import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.auth import get_current_user
from app.models import (
    Entity, EntityEntityLink, EntityMaterialLink, EntityFolderLink,
    Material, Folder, User,
)
from app.schemas import (
    EntityCreate, EntityUpdate, EntityResponse,
    EntityEntityLinkCreate, EntityMaterialLinkCreate, EntityFolderLinkCreate,
)
from app.activity import log_activity

logger = logging.getLogger("case-ims.entities")

router = APIRouter(prefix="/entities", tags=["Entities"])

VALID_TYPES = {"event", "person", "corporation", "topic"}


def _entity_response(e: Entity, db: Session) -> dict:
    mat_count = db.query(EntityMaterialLink).filter(EntityMaterialLink.entity_id == e.id).count()
    ent_count = db.query(EntityEntityLink).filter(
        or_(EntityEntityLink.entity_a_id == e.id, EntityEntityLink.entity_b_id == e.id)
    ).count()
    return {
        "id": e.id, "entity_type": e.entity_type, "case_id": e.case_id,
        "name": e.name, "description": e.description,
        "metadata_json": e.metadata_json or {},
        "event_date": e.event_date, "event_end_date": e.event_end_date,
        "event_location": e.event_location,
        "person_role": e.person_role, "person_id_number": e.person_id_number,
        "corp_type": e.corp_type, "corp_registration": e.corp_registration,
        "topic_color": e.topic_color, "topic_icon": e.topic_icon,
        "created_at": e.created_at,
        "material_link_count": mat_count, "entity_link_count": ent_count,
    }


# ---- Entity CRUD ----

@router.get("/")
def list_entities(
    case_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    size: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Entity)
    if case_id is not None:
        query = query.filter(Entity.case_id == case_id)
    if entity_type and entity_type in VALID_TYPES:
        query = query.filter(Entity.entity_type == entity_type)
    if q:
        query = query.filter(Entity.name.ilike(f"%{q}%"))

    total = query.count()
    entities = query.order_by(Entity.created_at.desc()).offset((page - 1) * size).limit(size).all()
    return {
        "total": total, "page": page, "size": size,
        "entities": [_entity_response(e, db) for e in entities],
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_entity(
    data: EntityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.entity_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity_type. Must be one of: {', '.join(VALID_TYPES)}")

    entity = Entity(
        entity_type=data.entity_type, case_id=data.case_id,
        name=data.name, description=data.description,
        metadata_json=data.metadata_json,
        event_date=data.event_date, event_end_date=data.event_end_date,
        event_location=data.event_location,
        person_role=data.person_role, person_id_number=data.person_id_number,
        corp_type=data.corp_type, corp_registration=data.corp_registration,
        topic_color=data.topic_color, topic_icon=data.topic_icon,
        created_by_id=current_user.id,
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    log_activity(db, "entity_created", f"Created {data.entity_type}: {data.name}",
                 user_id=current_user.id)
    return _entity_response(entity, db)


@router.get("/{entity_id}")
def get_entity(entity_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return _entity_response(entity, db)


@router.put("/{entity_id}")
def update_entity(
    entity_id: int, data: EntityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    for field in [
        "name", "description", "metadata_json",
        "event_date", "event_end_date", "event_location",
        "person_role", "person_id_number",
        "corp_type", "corp_registration",
        "topic_color", "topic_icon",
    ]:
        val = getattr(data, field, None)
        if val is not None:
            setattr(entity, field, val)

    db.commit()
    db.refresh(entity)
    return _entity_response(entity, db)


@router.delete("/{entity_id}")
def delete_entity(entity_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    log_activity(db, "entity_deleted", f"Deleted {entity.entity_type}: {entity.name}",
                 user_id=current_user.id)
    db.delete(entity)
    db.commit()
    return {"detail": "Entity deleted"}


# ---- Links: Entity ↔ Entity ----

@router.get("/{entity_id}/links")
def get_entity_links(entity_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Entity-entity links
    ee_links = db.query(EntityEntityLink).filter(
        or_(EntityEntityLink.entity_a_id == entity_id, EntityEntityLink.entity_b_id == entity_id)
    ).all()
    entity_links = []
    for link in ee_links:
        other_id = link.entity_b_id if link.entity_a_id == entity_id else link.entity_a_id
        other = db.query(Entity).filter(Entity.id == other_id).first()
        entity_links.append({
            "link_id": link.id,
            "entity_id": other_id,
            "entity_name": other.name if other else None,
            "entity_type": other.entity_type if other else None,
            "relationship_type": link.relationship_type,
            "relationship_detail": link.relationship_detail,
        })

    # Entity-material links
    em_links = db.query(EntityMaterialLink).filter(EntityMaterialLink.entity_id == entity_id).all()
    material_links = []
    for link in em_links:
        mat = db.query(Material).filter(Material.id == link.material_id).first()
        material_links.append({
            "link_id": link.id,
            "material_id": link.material_id,
            "filename": mat.filename if mat else None,
            "file_type": mat.file_type if mat else None,
            "relevance": link.relevance,
            "detail": link.detail,
            "page_ref": link.page_ref,
        })

    # Entity-folder links
    ef_links = db.query(EntityFolderLink).filter(EntityFolderLink.entity_id == entity_id).all()
    folder_links = []
    for link in ef_links:
        folder = db.query(Folder).filter(Folder.id == link.folder_id).first()
        folder_links.append({
            "link_id": link.id,
            "folder_id": link.folder_id,
            "folder_name": folder.name if folder else None,
            "detail": link.detail,
        })

    return {
        "entity_links": entity_links,
        "material_links": material_links,
        "folder_links": folder_links,
    }


@router.post("/{entity_id}/link-entity", status_code=status.HTTP_201_CREATED)
def link_entity_to_entity(
    entity_id: int,
    data: EntityEntityLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Ensure entity_id matches one side
    if entity_id not in (data.entity_a_id, data.entity_b_id):
        data.entity_a_id = entity_id

    if data.entity_a_id == data.entity_b_id:
        raise HTTPException(status_code=400, detail="Cannot link entity to itself")

    # Check both exist
    a = db.query(Entity).filter(Entity.id == data.entity_a_id).first()
    b = db.query(Entity).filter(Entity.id == data.entity_b_id).first()
    if not a or not b:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Check duplicate
    existing = db.query(EntityEntityLink).filter(
        or_(
            (EntityEntityLink.entity_a_id == data.entity_a_id) & (EntityEntityLink.entity_b_id == data.entity_b_id),
            (EntityEntityLink.entity_a_id == data.entity_b_id) & (EntityEntityLink.entity_b_id == data.entity_a_id),
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Link already exists")

    link = EntityEntityLink(
        entity_a_id=data.entity_a_id, entity_b_id=data.entity_b_id,
        relationship_type=data.relationship_type,
        relationship_detail=data.relationship_detail,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return {"id": link.id, "entity_a_id": link.entity_a_id, "entity_b_id": link.entity_b_id,
            "relationship_type": link.relationship_type}


@router.delete("/link-entity/{link_id}")
def unlink_entity_from_entity(link_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    link = db.query(EntityEntityLink).filter(EntityEntityLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    db.delete(link)
    db.commit()
    return {"detail": "Link removed"}


# ---- Links: Entity ↔ Material ----

@router.post("/{entity_id}/link-material", status_code=status.HTTP_201_CREATED)
def link_entity_to_material(
    entity_id: int,
    data: EntityMaterialLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data.entity_id = entity_id
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    mat = db.query(Material).filter(Material.id == data.material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="Material not found")

    existing = db.query(EntityMaterialLink).filter(
        EntityMaterialLink.entity_id == entity_id,
        EntityMaterialLink.material_id == data.material_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Link already exists")

    link = EntityMaterialLink(
        entity_id=entity_id, material_id=data.material_id,
        relevance=data.relevance, detail=data.detail, page_ref=data.page_ref,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return {"id": link.id, "entity_id": link.entity_id, "material_id": link.material_id}


@router.delete("/link-material/{link_id}")
def unlink_entity_from_material(link_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    link = db.query(EntityMaterialLink).filter(EntityMaterialLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    db.delete(link)
    db.commit()
    return {"detail": "Link removed"}


# ---- Links: Entity ↔ Folder ----

@router.post("/{entity_id}/link-folder", status_code=status.HTTP_201_CREATED)
def link_entity_to_folder(
    entity_id: int,
    data: EntityFolderLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data.entity_id = entity_id
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    folder = db.query(Folder).filter(Folder.id == data.folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    existing = db.query(EntityFolderLink).filter(
        EntityFolderLink.entity_id == entity_id,
        EntityFolderLink.folder_id == data.folder_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Link already exists")

    link = EntityFolderLink(
        entity_id=entity_id, folder_id=data.folder_id, detail=data.detail,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return {"id": link.id, "entity_id": link.entity_id, "folder_id": link.folder_id}


@router.delete("/link-folder/{link_id}")
def unlink_entity_from_folder(link_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    link = db.query(EntityFolderLink).filter(EntityFolderLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    db.delete(link)
    db.commit()
    return {"detail": "Link removed"}


# ---- Bulk: get materials linked to entity (with folder expansion) ----

@router.get("/{entity_id}/materials")
def get_entity_materials(entity_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get all materials linked to this entity, including materials in linked folders."""
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Direct material links
    direct_links = db.query(EntityMaterialLink).filter(EntityMaterialLink.entity_id == entity_id).all()
    direct_ids = {l.material_id for l in direct_links}

    # Materials from linked folders
    folder_links = db.query(EntityFolderLink).filter(EntityFolderLink.entity_id == entity_id).all()
    folder_ids = [l.folder_id for l in folder_links]
    folder_material_ids = set()
    if folder_ids:
        folder_mats = db.query(Material.id).filter(Material.folder_id.in_(folder_ids)).all()
        folder_material_ids = {m.id for m in folder_mats}

    all_ids = direct_ids | folder_material_ids
    if not all_ids:
        return {"materials": []}

    materials = db.query(Material).filter(Material.id.in_(all_ids)).order_by(Material.upload_date.desc()).all()
    return {
        "materials": [
            {
                "id": m.id, "filename": m.filename, "file_type": m.file_type,
                "file_size": m.file_size, "case_id": m.case_id,
                "upload_date": m.upload_date,
                "content_summary": m.content_summary,
                "is_direct": m.id in direct_ids,
                "is_from_folder": m.id in folder_material_ids,
            }
            for m in materials
        ]
    }
