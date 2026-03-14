import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.database import get_db
from app.auth import get_current_user
from app.models import MaterialGroup, MaterialGroupMember, Material, User
from app.schemas import GroupCreate, GroupUpdate, GroupAddMembers
from app.activity import log_activity
from app import llm_service

logger = logging.getLogger("case-dms.groups")

router = APIRouter(prefix="/groups", tags=["Material Groups"])


def _group_response(g: MaterialGroup, db: Session) -> dict:
    member_count = db.query(MaterialGroupMember).filter(MaterialGroupMember.group_id == g.id).count()
    return {
        "id": g.id, "case_id": g.case_id, "name": g.name,
        "description": g.description,
        "analysis_result": g.analysis_result,
        "analysis_metadata": g.analysis_metadata or {},
        "member_count": member_count,
        "created_at": g.created_at,
        "updated_at": g.updated_at,
    }


@router.get("/")
def list_groups(
    case_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(MaterialGroup)
    if case_id is not None:
        query = query.filter(MaterialGroup.case_id == case_id)
    groups = query.order_by(MaterialGroup.created_at.desc()).all()
    return {"groups": [_group_response(g, db) for g in groups]}


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_group(
    data: GroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = MaterialGroup(
        case_id=data.case_id, name=data.name,
        description=data.description, created_by_id=current_user.id,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    log_activity(db, "group_created", f"Created group: {data.name}", user_id=current_user.id)
    return _group_response(group, db)


@router.get("/{group_id}")
def get_group(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    group = db.query(MaterialGroup).filter(MaterialGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    resp = _group_response(group, db)

    # Include members
    members = (
        db.query(MaterialGroupMember, Material)
        .join(Material, MaterialGroupMember.material_id == Material.id)
        .filter(MaterialGroupMember.group_id == group_id)
        .order_by(MaterialGroupMember.added_at.desc())
        .all()
    )
    resp["members"] = [
        {
            "membership_id": mem.id, "material_id": mat.id,
            "filename": mat.filename, "file_type": mat.file_type,
            "file_size": mat.file_size, "content_summary": mat.content_summary,
            "extraction_status": mat.extraction_status,
            "added_at": mem.added_at,
        }
        for mem, mat in members
    ]

    return resp


@router.put("/{group_id}")
def update_group(
    group_id: int, data: GroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(MaterialGroup).filter(MaterialGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if data.name is not None:
        group.name = data.name
    if data.description is not None:
        group.description = data.description
    db.commit()
    db.refresh(group)
    return _group_response(group, db)


@router.delete("/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    group = db.query(MaterialGroup).filter(MaterialGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    log_activity(db, "group_deleted", f"Deleted group: {group.name}", user_id=current_user.id)
    db.delete(group)
    db.commit()
    return {"detail": "Group deleted"}


# ---- Members ----

@router.post("/{group_id}/members", status_code=status.HTTP_201_CREATED)
def add_members(
    group_id: int, data: GroupAddMembers,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(MaterialGroup).filter(MaterialGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    added = 0
    skipped = 0
    for mid in data.material_ids:
        mat = db.query(Material).filter(Material.id == mid).first()
        if not mat:
            continue
        existing = db.query(MaterialGroupMember).filter(
            MaterialGroupMember.group_id == group_id,
            MaterialGroupMember.material_id == mid,
        ).first()
        if existing:
            skipped += 1
            continue
        db.add(MaterialGroupMember(group_id=group_id, material_id=mid))
        added += 1

    db.commit()
    return {"added": added, "skipped": skipped}


@router.delete("/{group_id}/members/{material_id}")
def remove_member(
    group_id: int, material_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    member = db.query(MaterialGroupMember).filter(
        MaterialGroupMember.group_id == group_id,
        MaterialGroupMember.material_id == material_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found in group")
    db.delete(member)
    db.commit()
    return {"detail": "Member removed"}


# ---- Group Analysis ----

@router.post("/{group_id}/analyze")
def analyze_group(
    group_id: int,
    provider: str = "deepseek",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run AI analysis on all materials in this group (cross-document analysis)."""
    group = db.query(MaterialGroup).filter(MaterialGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    key_error = llm_service.check_provider_key(provider)
    if key_error:
        raise HTTPException(status_code=400, detail=key_error)

    # Gather member texts
    members = (
        db.query(Material)
        .join(MaterialGroupMember, MaterialGroupMember.material_id == Material.id)
        .filter(MaterialGroupMember.group_id == group_id)
        .all()
    )
    if not members:
        raise HTTPException(status_code=400, detail="Group has no members")

    # Build combined text for analysis
    combined_parts = []
    for mat in members:
        text = mat.content_text or ""
        summary = mat.content_summary or ""
        section = f"--- {mat.filename} ---\n"
        if summary:
            section += f"Summary: {summary}\n"
        if text:
            # Truncate long texts
            section += text[:10000] + ("\n[...truncated]" if len(text) > 10000 else "")
        combined_parts.append(section)

    combined_text = "\n\n".join(combined_parts)

    # Truncate total if too large
    if len(combined_text) > 50000:
        combined_text = combined_text[:50000] + "\n\n[...total text truncated]"

    prompt = (
        "You are an investigative analyst. Analyze the following group of documents together.\n"
        "Identify:\n"
        "1. Common themes and patterns across documents\n"
        "2. Key relationships between people, organizations, and events mentioned\n"
        "3. Timeline of events if applicable\n"
        "4. Contradictions or discrepancies between documents\n"
        "5. Overall summary of the document collection\n\n"
        "Respond in Hebrew.\n\n"
        f"Group name: {group.name}\n"
        f"Number of documents: {len(members)}\n\n"
        f"{combined_text}"
    )

    try:
        result = llm_service.call_llm(prompt, provider=provider, max_tokens=4000)
        group.analysis_result = result
        group.analysis_metadata = {
            "provider": provider,
            "member_count": len(members),
            "total_text_length": len(combined_text),
            "filenames": [m.filename for m in members],
        }
        flag_modified(group, "analysis_metadata")
        db.commit()
        log_activity(db, "group_analyzed", f"Group analyzed: {group.name} ({len(members)} docs)",
                     user_id=current_user.id)
        return {
            "analysis_result": result,
            "member_count": len(members),
        }
    except Exception as e:
        logger.error("Group analysis failed for %d: %s", group_id, e)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)[:200]}")
