import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user, get_current_admin_user
from app.models import Case, Material, Entity, User
from app.schemas import CaseCreate, CaseUpdate, CaseResponse

logger = logging.getLogger("case-dms.cases")

router = APIRouter(prefix="/cases", tags=["Cases"])


@router.get("/")
def list_cases(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cases = db.query(Case).filter(Case.is_active.is_(True)).order_by(Case.created_at.desc()).all()
    result = []
    for c in cases:
        mat_count = db.query(Material).filter(Material.case_id == c.id).count()
        ent_count = db.query(Entity).filter(Entity.case_id == c.id).count()
        result.append({
            "id": c.id, "name": c.name, "description": c.description,
            "icon": c.icon, "color": c.color, "is_active": c.is_active,
            "material_count": mat_count, "entity_count": ent_count,
            "created_at": c.created_at,
        })
    return result


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_case(data: CaseCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    existing = db.query(Case).filter(Case.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Case name already exists")
    case = Case(
        name=data.name, description=data.description,
        icon=data.icon, color=data.color, created_by_id=current_user.id,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return {
        "id": case.id, "name": case.name, "description": case.description,
        "icon": case.icon, "color": case.color, "is_active": case.is_active,
        "material_count": 0, "entity_count": 0, "created_at": case.created_at,
    }


@router.get("/{case_id}")
def get_case(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    mat_count = db.query(Material).filter(Material.case_id == case.id).count()
    ent_count = db.query(Entity).filter(Entity.case_id == case.id).count()
    return {
        "id": case.id, "name": case.name, "description": case.description,
        "icon": case.icon, "color": case.color, "is_active": case.is_active,
        "metadata_json": case.metadata_json or {},
        "material_count": mat_count, "entity_count": ent_count,
        "created_at": case.created_at,
    }


@router.put("/{case_id}")
def update_case(case_id: int, data: CaseUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if data.name is not None:
        case.name = data.name
    if data.description is not None:
        case.description = data.description
    if data.icon is not None:
        case.icon = data.icon
    if data.color is not None:
        case.color = data.color
    if data.is_active is not None:
        case.is_active = data.is_active
    db.commit()
    db.refresh(case)
    return {"id": case.id, "name": case.name, "description": case.description,
            "icon": case.icon, "color": case.color, "is_active": case.is_active,
            "created_at": case.created_at}


@router.delete("/{case_id}")
def delete_case(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    db.delete(case)
    db.commit()
    return {"detail": "Case deleted"}
