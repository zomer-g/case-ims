import os
import hashlib
import json
import logging
import mimetypes
from typing import Optional
from datetime import datetime
from urllib.parse import quote as url_quote
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from jose import JWTError, jwt as jose_jwt

from app.database import get_db, SessionLocal
from app.config import settings
from app.auth import get_current_user, get_current_admin_user, get_optional_user
from app import models, schemas
from app.workflow import run_material_workflow
from app import llm_service
from app.activity import log_activity
from app.extractors import classify_file_type

logger = logging.getLogger("case-ims.materials")

UPLOAD_DIR = settings.UPLOAD_DIR
router = APIRouter(prefix="/materials", tags=["Materials"])

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

_MIME_MAP = {
    '.pdf': 'application/pdf', '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.txt': 'text/plain', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.html': 'text/html', '.htm': 'text/html',
    '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.m4a': 'audio/mp4',
    '.mp4': 'video/mp4', '.avi': 'video/x-msvideo', '.mov': 'video/quicktime',
    '.csv': 'text/csv', '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}


def _compute_file_hash(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def _extract_page_count(file_path: str, ext: str) -> Optional[int]:
    if ext == '.pdf':
        try:
            from pypdf import PdfReader
            return len(PdfReader(file_path).pages)
        except Exception:
            return None
    return None


def _resolve_folder_from_path(db: Session, case_id: Optional[int], relative_path: str) -> Optional[int]:
    """Given a relative path like 'folder/subfolder', auto-create Folder records and return leaf folder_id."""
    if not relative_path or not case_id:
        return None

    # Sanitize: remove leading/trailing slashes, normalize separators
    relative_path = relative_path.replace("\\", "/").strip("/")
    if not relative_path:
        return None

    parts = [p.strip() for p in relative_path.split("/") if p.strip()]
    if not parts:
        return None

    parent_id = None
    for part in parts:
        # Sanitize folder name
        safe_name = part.replace("..", "_").replace("\x00", "")[:255]
        if not safe_name:
            safe_name = "folder"

        # Look for existing folder with this name under same parent
        existing = db.query(models.Folder).filter(
            models.Folder.case_id == case_id,
            models.Folder.name == safe_name,
            models.Folder.parent_folder_id == parent_id,
            models.Folder.source_type == "upload",
        ).first()

        if existing:
            parent_id = existing.id
        else:
            # Build full path for display
            folder = models.Folder(
                case_id=case_id,
                name=safe_name,
                path=relative_path,
                source_type="upload",
                parent_folder_id=parent_id,
            )
            db.add(folder)
            db.flush()  # get the id
            parent_id = folder.id

    return parent_id


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_material(
    request: Request,
    file: UploadFile = File(...),
    case_id: Optional[int] = Form(None),
    folder_id: Optional[int] = Form(None),
    relative_path: Optional[str] = Form(None),
    provider: str = Form("deepseek"),
    is_public: Optional[bool] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Check upload limit
    if current_user.max_upload_docs and current_user.max_upload_docs > 0:
        count = db.query(models.Material).filter(models.Material.owner_id == current_user.id).count()
        if count >= current_user.max_upload_docs:
            raise HTTPException(status_code=403, detail=f"\u05d4\u05d2\u05e2\u05ea \u05dc\u05de\u05db\u05e1\u05d4 {current_user.max_upload_docs} \u05e7\u05d1\u05e6\u05d9\u05dd")
    if current_user.max_upload_docs == -1:
        raise HTTPException(status_code=403, detail="\u05d4\u05e2\u05dc\u05d0\u05ea \u05e7\u05d1\u05e6\u05d9\u05dd \u05d7\u05e1\u05d5\u05de\u05d4")

    # Auto-resolve folder from relative_path if provided and no explicit folder_id
    if relative_path and not folder_id and case_id:
        folder_id = _resolve_folder_from_path(db, case_id, relative_path)

    # Check file size
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"\u05d2\u05d5\u05d3\u05dc \u05d4\u05e7\u05d5\u05d1\u05e5 \u05d7\u05d5\u05e8\u05d2 \u05de-{settings.MAX_UPLOAD_SIZE_MB}MB")

    # Validate file extension
    _ALLOWED_EXTENSIONS = {
        '.pdf', '.doc', '.docx', '.pptx', '.txt', '.html', '.htm',
        '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp', '.webp', '.gif',
        '.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac',
        '.mp4', '.avi', '.mov', '.mkv', '.webm',
        '.csv', '.xlsx', '.xls', '.tsv',
    }
    raw_ext = os.path.splitext(file.filename or "")[1].lower()
    if raw_ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"\u05e1\u05d5\u05d2 \u05e7\u05d5\u05d1\u05e5 \u05dc\u05d0 \u05e0\u05ea\u05de\u05da: {raw_ext}")

    # Save file — sanitize filename to prevent path traversal
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_filename = os.path.basename(file.filename or "upload").replace("/", "_").replace("\\", "_")
    safe_filename = safe_filename.replace("..", "_").replace("\x00", "_")
    if not safe_filename or safe_filename.startswith("."):
        safe_filename = "upload" + raw_ext
    stored_name = f"{current_user.id}_{timestamp}_{safe_filename}"
    file_path = os.path.join(UPLOAD_DIR, stored_name)

    # Final safety: ensure resolved path is inside UPLOAD_DIR
    if not os.path.realpath(file_path).startswith(os.path.realpath(UPLOAD_DIR)):
        raise HTTPException(status_code=400, detail="Invalid filename")

    with open(file_path, "wb") as f:
        f.write(content)

    ext = os.path.splitext(safe_filename)[1].lower()
    file_type = classify_file_type(safe_filename)
    mime_type = _MIME_MAP.get(ext) or mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
    file_hash = _compute_file_hash(file_path)

    # Check dedup
    existing = db.query(models.Material).filter(
        models.Material.file_hash == file_hash,
        models.Material.case_id == case_id,
    ).first()
    if existing:
        os.remove(file_path)
        raise HTTPException(status_code=409, detail=f"\u05e7\u05d5\u05d1\u05e5 \u05d6\u05d4\u05d4 \u05db\u05d1\u05e8 \u05e7\u05d9\u05d9\u05dd: {existing.filename}")

    visibility = is_public if is_public is not None else (current_user.default_visibility == "public")
    page_count = _extract_page_count(file_path, ext)

    # Store original relative path for folder imports
    original_path = None
    if relative_path:
        original_path = (relative_path.replace("\\", "/").strip("/") + "/" + safe_filename)

    material = models.Material(
        owner_id=current_user.id, case_id=case_id, folder_id=folder_id,
        filename=safe_filename, file_path=file_path,
        original_path=original_path,
        file_type=file_type, mime_type=mime_type,
        file_size=len(content), file_hash=file_hash,
        is_public=visibility, page_count=page_count,
        metadata_json={},
    )
    db.add(material)
    db.commit()
    db.refresh(material)

    from app.activity import _parse_ua
    log_activity(db, "upload", f"Uploaded: {safe_filename} ({file_type})",
                 user_id=current_user.id, material_id=material.id,
                 user_agent=_parse_ua(request.headers.get("user-agent", "")))

    # Queue for processing
    key_error = llm_service.check_provider_key(provider)
    if not key_error:
        queue_item = models.ProcessingQueue(
            material_id=material.id, user_id=current_user.id,
            provider=provider, status="pending",
        )
        db.add(queue_item)
        db.commit()

    return {
        "id": material.id, "filename": material.filename,
        "file_type": material.file_type, "file_size": material.file_size,
        "case_id": material.case_id, "upload_date": material.upload_date,
        "queued": not bool(key_error),
    }


@router.get("/")
def list_materials(
    case_id: Optional[int] = None,
    folder_id: Optional[int] = None,
    file_type: Optional[str] = None,
    q: Optional[str] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_dir: Optional[str] = None,
    page: int = 1,
    size: int = 50,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_optional_user),
):
    from sqlalchemy import or_
    query = db.query(models.Material)

    # Visibility filter
    if current_user and current_user.is_admin:
        pass  # Admin sees all
    elif current_user:
        query = query.filter(or_(
            models.Material.is_public.is_(True),
            models.Material.owner_id == current_user.id,
        ))
    else:
        query = query.filter(models.Material.is_public.is_(True))

    if case_id is not None:
        query = query.filter(models.Material.case_id == case_id)
    if folder_id is not None:
        query = query.filter(models.Material.folder_id == folder_id)
    if file_type:
        query = query.filter(models.Material.file_type == file_type)
    if status:
        query = query.filter(models.Material.extraction_status == status)
    if q:
        query = query.filter(models.Material.filename.ilike(f"%{q}%"))
    if search:
        query = query.filter(or_(
            models.Material.filename.ilike(f"%{search}%"),
            models.Material.content_text.ilike(f"%{search}%"),
            models.Material.content_summary.ilike(f"%{search}%"),
        ))

    total = query.count()

    # Sorting
    _sort_columns = {
        "filename": models.Material.filename,
        "upload_date": models.Material.upload_date,
        "file_size": models.Material.file_size,
        "file_type": models.Material.file_type,
    }
    sort_col = _sort_columns.get(sort_by, models.Material.upload_date)
    if sort_dir == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    materials = query.offset((page - 1) * size).limit(size).all()

    return {
        "total": total, "page": page, "size": size,
        "materials": [
            {
                "id": m.id, "filename": m.filename, "file_type": m.file_type,
                "file_size": m.file_size, "case_id": m.case_id,
                "case_name": m.case_name, "folder_id": m.folder_id,
                "folder_name": m.folder.name if m.folder else None,
                "upload_date": m.upload_date, "is_public": m.is_public,
                "content_summary": m.content_summary,
                "metadata_json": m.metadata_json or {},
                "extraction_status": m.extraction_status,
                "page_count": m.page_count, "duration_seconds": m.duration_seconds,
                "original_path": m.original_path,
            }
            for m in materials
        ],
    }


@router.get("/{material_id}")
def get_material(material_id: int, db: Session = Depends(get_db), current_user: Optional[models.User] = Depends(get_optional_user)):
    mat = db.query(models.Material).filter(models.Material.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="Material not found")

    # Visibility check
    if not mat.is_public:
        if not current_user or (not current_user.is_admin and current_user.id != mat.owner_id):
            raise HTTPException(status_code=403, detail="Access denied")

    return {
        "id": mat.id, "filename": mat.filename,
        "file_type": mat.file_type, "mime_type": mat.mime_type,
        "file_size": mat.file_size, "file_hash": mat.file_hash,
        "owner_id": mat.owner_id, "case_id": mat.case_id, "case_name": mat.case_name,
        "folder_id": mat.folder_id, "upload_date": mat.upload_date,
        "content_text": mat.content_text or "", "content_summary": mat.content_summary,
        "metadata_json": mat.metadata_json or {},
        "is_public": mat.is_public, "extraction_status": mat.extraction_status,
        "page_count": mat.page_count, "duration_seconds": mat.duration_seconds,
        "dimensions": mat.dimensions,
    }


@router.get("/{material_id}/download")
def download_material(material_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    mat = db.query(models.Material).filter(models.Material.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="Material not found")
    if not os.path.exists(mat.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")
    encoded = url_quote(mat.filename)
    return FileResponse(
        mat.file_path,
        media_type=mat.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename*=UTF-8\'\'{encoded}'},
    )


@router.get("/{material_id}/view-token")
def get_view_token(material_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    mat = db.query(models.Material).filter(models.Material.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="Material not found")
    from app.auth import create_view_token
    token = create_view_token(current_user.email, material_id)
    return {"token": token}


@router.patch("/{material_id}")
def update_material(material_id: int, data: schemas.MaterialUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    mat = db.query(models.Material).filter(models.Material.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="Material not found")
    if not current_user.is_admin and current_user.id != mat.owner_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if data.is_public is not None:
        mat.is_public = data.is_public
    if data.metadata_json is not None:
        mat.metadata_json = data.metadata_json
        flag_modified(mat, "metadata_json")
    db.commit()
    return {"id": mat.id, "updated": True}


@router.post("/{material_id}/reprocess")
def reprocess_material(
    material_id: int,
    provider: str = "deepseek",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    mat = db.query(models.Material).filter(models.Material.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="Material not found")
    key_error = llm_service.check_provider_key(provider)
    if key_error:
        raise HTTPException(status_code=400, detail=key_error)

    queue_item = models.ProcessingQueue(
        material_id=mat.id, user_id=current_user.id,
        provider=provider, status="pending",
    )
    db.add(queue_item)
    db.commit()
    log_activity(db, "reprocess", f"Reprocess queued: {mat.filename}", user_id=current_user.id, material_id=mat.id)
    return {"queued": True, "queue_id": queue_item.id}


@router.delete("/{material_id}")
def delete_material(material_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    mat = db.query(models.Material).filter(models.Material.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="Material not found")
    if not current_user.is_admin and current_user.id != mat.owner_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Remove file from disk
    if os.path.exists(mat.file_path):
        os.remove(mat.file_path)
    md_path = f"{mat.file_path}.md"
    if os.path.exists(md_path):
        os.remove(md_path)

    log_activity(db, "delete", f"Deleted: {mat.filename}", user_id=current_user.id, material_id=mat.id)
    db.delete(mat)
    db.commit()
    return {"detail": "Material deleted"}


@router.post("/bulk/tag")
def bulk_tag_materials(
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Add a tag to multiple materials' metadata_json."""
    material_ids = data.get("material_ids", [])
    tag = data.get("tag", "").strip()
    if not material_ids or not tag:
        raise HTTPException(status_code=400, detail="material_ids and tag required")

    updated = 0
    for mid in material_ids:
        mat = db.query(models.Material).filter(models.Material.id == mid).first()
        if not mat:
            continue
        meta = mat.metadata_json or {}
        tags = meta.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        if tag not in tags:
            tags.append(tag)
        meta["tags"] = tags
        mat.metadata_json = meta
        flag_modified(mat, "metadata_json")
        updated += 1

    db.commit()
    return {"updated": updated, "tag": tag}


@router.post("/bulk/link-entities")
def bulk_link_entities(
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Link multiple materials to entities, optionally creating new entities."""
    material_ids = data.get("material_ids", [])
    entity_ids = data.get("entity_ids", [])
    create_entities = data.get("create_entities", [])
    if not material_ids:
        raise HTTPException(status_code=400, detail="material_ids required")

    # Create new entities if requested
    for ent_data in create_entities:
        name = ent_data.get("name", "").strip()
        etype = ent_data.get("entity_type", "topic")
        case_id = ent_data.get("case_id")
        if not name or not case_id:
            continue
        entity = models.Entity(
            entity_type=etype, case_id=case_id, name=name,
            created_by_id=current_user.id,
        )
        db.add(entity)
        db.flush()
        entity_ids.append(entity.id)

    linked = 0
    for mid in material_ids:
        mat = db.query(models.Material).filter(models.Material.id == mid).first()
        if not mat:
            continue
        for eid in entity_ids:
            existing = db.query(models.EntityMaterialLink).filter(
                models.EntityMaterialLink.entity_id == eid,
                models.EntityMaterialLink.material_id == mid,
            ).first()
            if not existing:
                link = models.EntityMaterialLink(entity_id=eid, material_id=mid)
                db.add(link)
                linked += 1

    db.commit()
    return {"linked": linked}


@router.post("/bulk/link-timeline")
def bulk_link_timeline(
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Link multiple materials to timeline events, optionally creating new events."""
    material_ids = data.get("material_ids", [])
    event_ids = data.get("event_ids", [])
    create_events = data.get("create_events", [])
    if not material_ids:
        raise HTTPException(status_code=400, detail="material_ids required")

    # Create new events if requested
    for ev_data in create_events:
        title = ev_data.get("title", "").strip()
        event_date = ev_data.get("event_date")
        case_id = ev_data.get("case_id")
        if not title or not event_date or not case_id:
            continue
        ev = models.TimelineEvent(
            case_id=case_id, title=title, event_date=event_date,
            description=ev_data.get("description"),
            location=ev_data.get("location"),
            source="manual",
        )
        db.add(ev)
        db.flush()
        event_ids.append(ev.id)

    # For timeline events, we set material_id on the event itself
    # Since TimelineEvent has a single material_id, we create copies for each material
    linked = 0
    for mid in material_ids:
        mat = db.query(models.Material).filter(models.Material.id == mid).first()
        if not mat:
            continue
        for eid in event_ids:
            ev = db.query(models.TimelineEvent).filter(models.TimelineEvent.id == eid).first()
            if not ev:
                continue
            # If event has no material_id, set it
            if ev.material_id is None:
                ev.material_id = mid
                linked += 1
            elif ev.material_id != mid:
                # Create a clone of this event linked to this material
                new_ev = models.TimelineEvent(
                    case_id=ev.case_id, material_id=mid,
                    title=ev.title, description=ev.description,
                    event_date=ev.event_date, event_end_date=ev.event_end_date,
                    location=ev.location, source=ev.source,
                    confidence=ev.confidence, tags=ev.tags,
                )
                db.add(new_ev)
                linked += 1

    db.commit()
    return {"linked": linked}


@router.get("/{material_id}/entities")
def get_material_entities(material_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Get all entities linked to a material."""
    mat = db.query(models.Material).filter(models.Material.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="Material not found")

    links = db.query(models.EntityMaterialLink).filter(
        models.EntityMaterialLink.material_id == material_id
    ).all()

    results = []
    for link in links:
        entity = link.entity
        results.append({
            "link_id": link.id,
            "entity_id": entity.id,
            "entity_type": entity.entity_type,
            "name": entity.name,
            "description": entity.description,
            "relevance": link.relevance,
            "detail": link.detail,
            "page_ref": link.page_ref,
        })
    return {"entities": results}


@router.get("/{material_id}/timeline-events")
def get_material_timeline_events(material_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Get all timeline events linked to a material."""
    mat = db.query(models.Material).filter(models.Material.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="Material not found")

    events = db.query(models.TimelineEvent).filter(
        models.TimelineEvent.material_id == material_id
    ).order_by(models.TimelineEvent.event_date).all()

    return {
        "events": [
            {
                "id": ev.id, "title": ev.title, "description": ev.description,
                "event_date": ev.event_date, "event_end_date": ev.event_end_date,
                "location": ev.location, "source": ev.source,
                "confidence": ev.confidence, "tags": ev.tags or [],
            }
            for ev in events
        ]
    }


def background_ai_task(material_id: int, text: str, file_path: str, provider: str):
    """Run AI analysis on a material (called by queue_processor)."""
    db = SessionLocal()
    try:
        mat = db.query(models.Material).filter(models.Material.id == material_id).first()
        if not mat:
            return

        result = run_material_workflow(material_id, text, db, provider=provider, case_id=mat.case_id)

        # Merge into metadata_json
        existing_meta = mat.metadata_json or {}
        existing_meta["ai_analysis"] = result
        mat.metadata_json = existing_meta
        flag_modified(mat, "metadata_json")

        # Extract summary from AI result
        summary = result.get("summary") or result.get("\u05ea\u05e7\u05e6\u05d9\u05e8") or ""
        if summary:
            mat.content_summary = summary

        mat.extraction_status = "done"
        db.commit()

        log_activity(db, "analysis_completed", f"AI analysis done: {mat.filename}",
                     material_id=material_id, commit=True)
    except Exception as e:
        db.rollback()
        logger.error("AI task failed for material %d: %s", material_id, e)
        try:
            mat = db.query(models.Material).filter(models.Material.id == material_id).first()
            if mat:
                mat.extraction_status = "failed"
                mat.extraction_error = str(e)[:500]
                db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        db.close()
