"""Admin detected field management."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_admin_user
from app.models import DetectedField, User

logger = logging.getLogger("case-ims.admin-fields")

router = APIRouter(prefix="/admin/fields", tags=["Admin – Fields"])


@router.get("/")
def list_fields(db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    fields = db.query(DetectedField).order_by(DetectedField.field_key).all()
    return [
        {
            "id": f.id, "field_key": f.field_key,
            "friendly_name": f.friendly_name,
            "field_type": f.field_type,
            "is_array": f.is_array,
            "first_seen": f.first_seen,
        }
        for f in fields
    ]


@router.put("/{field_id}")
def update_field(field_id: int, data: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    field = db.query(DetectedField).filter(DetectedField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")

    if "friendly_name" in data:
        field.friendly_name = data["friendly_name"]
    if "field_type" in data:
        field.field_type = data["field_type"]
    if "is_array" in data:
        field.is_array = data["is_array"]

    db.commit()
    return {"id": field.id, "updated": True}


@router.delete("/{field_id}")
def delete_field(field_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    field = db.query(DetectedField).filter(DetectedField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    db.delete(field)
    db.commit()
    return {"detail": "Field deleted"}
