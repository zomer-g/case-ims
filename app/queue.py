import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models import ProcessingQueue, Material, User
from app.schemas import QueueAddRequest, QueueStatusResponse, QueueStatusItem
from app import llm_service

logger = logging.getLogger("case-ims.queue-api")

router = APIRouter(prefix="/queue", tags=["Queue"])


@router.post("/add")
def add_to_queue(data: QueueAddRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    key_error = llm_service.check_provider_key(data.provider)
    if key_error:
        raise HTTPException(status_code=400, detail=key_error)

    added = []
    skipped = []
    for mid in data.material_ids:
        mat = db.query(Material).filter(Material.id == mid).first()
        if not mat:
            skipped.append(mid)
            continue

        # Skip if already pending/running
        existing = db.query(ProcessingQueue).filter(
            ProcessingQueue.material_id == mid,
            ProcessingQueue.status.in_(["pending", "running"]),
        ).first()
        if existing:
            skipped.append(mid)
            continue

        item = ProcessingQueue(
            material_id=mid, user_id=current_user.id,
            provider=data.provider, status="pending",
            priority=data.priority,
        )
        db.add(item)
        db.flush()
        added.append({"material_id": mid, "queue_id": item.id, "filename": mat.filename, "status": "pending"})

    db.commit()
    return {"added": added, "skipped": skipped}


@router.get("/status")
def queue_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = (
        db.query(ProcessingQueue)
        .filter(ProcessingQueue.status.in_(["pending", "running"]))
        .order_by(ProcessingQueue.priority.asc(), ProcessingQueue.queued_at.asc())
        .all()
    )

    result = []
    for i, item in enumerate(items):
        mat = db.query(Material).filter(Material.id == item.material_id).first()
        result.append(QueueStatusItem(
            queue_id=item.id, material_id=item.material_id,
            filename=mat.filename if mat else None,
            status=item.status, provider=item.provider,
            position=i + 1 if item.status == "pending" else None,
            error_detail=item.error_detail,
            queued_at=item.queued_at.isoformat() if item.queued_at else None,
        ))

    running_count = sum(1 for i in items if i.status == "running")
    pending_count = sum(1 for i in items if i.status == "pending")

    return QueueStatusResponse(items=result, running_count=running_count, pending_count=pending_count)
