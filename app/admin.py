"""Admin dashboard endpoints."""

import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.database import get_db
from app.auth import get_current_admin_user
from app.models import User, Material, Case, Entity, ProcessingQueue, ActivityLog

logger = logging.getLogger("case-dms.admin")

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats")
def admin_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    users_count = db.query(User).count()
    materials_count = db.query(Material).count()
    cases_count = db.query(Case).count()
    entities_count = db.query(Entity).count()
    pending_queue = db.query(ProcessingQueue).filter(ProcessingQueue.status == "pending").count()
    running_queue = db.query(ProcessingQueue).filter(ProcessingQueue.status == "running").count()

    # Materials by type
    type_counts = dict(
        db.query(Material.file_type, sa_func.count(Material.id))
        .group_by(Material.file_type).all()
    )

    # Materials by extraction status
    status_counts = dict(
        db.query(Material.extraction_status, sa_func.count(Material.id))
        .group_by(Material.extraction_status).all()
    )

    return {
        "users": users_count,
        "materials": materials_count,
        "cases": cases_count,
        "entities": entities_count,
        "queue_pending": pending_queue,
        "queue_running": running_queue,
        "materials_by_type": type_counts,
        "materials_by_status": status_counts,
    }


@router.get("/activity")
def admin_activity(
    page: int = 1,
    size: int = 50,
    event_type: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    query = db.query(ActivityLog)
    if event_type:
        query = query.filter(ActivityLog.event_type == event_type)
    total = query.count()
    items = (
        query.order_by(ActivityLog.timestamp.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [
            {
                "id": a.id,
                "timestamp": a.timestamp,
                "event_type": a.event_type,
                "user_id": a.user_id,
                "material_id": a.material_id,
                "detail": a.detail,
                "level": a.level,
                "user_agent": a.user_agent,
            }
            for a in items
        ],
    }
