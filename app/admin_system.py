"""Admin system settings management."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_admin_user
from app.models import SiteSetting, User

logger = logging.getLogger("case-dms.admin-system")

router = APIRouter(prefix="/admin/system", tags=["Admin – System"])


@router.get("/settings")
def list_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    settings = db.query(SiteSetting).order_by(SiteSetting.key).all()
    return [{"id": s.id, "key": s.key, "value": s.value, "updated_at": s.updated_at} for s in settings]


@router.put("/settings/{key}")
def upsert_setting(key: str, data: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    value = data.get("value")
    if value is None:
        raise HTTPException(status_code=400, detail="value is required")

    setting = db.query(SiteSetting).filter(SiteSetting.key == key).first()
    if setting:
        setting.value = str(value)
    else:
        setting = SiteSetting(key=key, value=str(value))
        db.add(setting)

    db.commit()
    return {"key": key, "value": str(value), "updated": True}


@router.delete("/settings/{key}")
def delete_setting(key: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    setting = db.query(SiteSetting).filter(SiteSetting.key == key).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    db.delete(setting)
    db.commit()
    return {"detail": "Setting deleted"}
