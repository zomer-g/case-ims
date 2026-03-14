import logging
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database import get_db
from app.auth import get_current_user
from app.models import TimelineEvent, Material, Entity, User
from app.schemas import TimelineEventCreate, TimelineEventUpdate, TimelineGenerateRequest
from app.activity import log_activity
from app import llm_service

logger = logging.getLogger("case-ims.timeline")

router = APIRouter(prefix="/timeline", tags=["Timeline"])


def _event_response(e: TimelineEvent, db: Session) -> dict:
    mat = db.query(Material).filter(Material.id == e.material_id).first() if e.material_id else None
    ent = db.query(Entity).filter(Entity.id == e.entity_id).first() if e.entity_id else None
    return {
        "id": e.id, "case_id": e.case_id,
        "title": e.title, "description": e.description,
        "event_date": e.event_date,
        "event_end_date": e.event_end_date,
        "location": e.location,
        "source": e.source, "confidence": e.confidence,
        "tags": e.tags or [],
        "metadata_json": e.metadata_json or {},
        "material_id": e.material_id,
        "material_filename": mat.filename if mat else None,
        "entity_id": e.entity_id,
        "entity_name": ent.name if ent else None,
        "entity_type": ent.entity_type if ent else None,
        "created_at": e.created_at,
    }


@router.get("/")
def list_timeline_events(
    case_id: int = Query(..., description="Case ID is required"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    entity_id: Optional[int] = None,
    material_id: Optional[int] = None,
    source: Optional[str] = None,
    tag: Optional[str] = None,
    page: int = 1,
    size: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(TimelineEvent)
    if case_id is not None:
        query = query.filter(TimelineEvent.case_id == case_id)
    if entity_id is not None:
        query = query.filter(TimelineEvent.entity_id == entity_id)
    if material_id is not None:
        query = query.filter(TimelineEvent.material_id == material_id)
    if source:
        query = query.filter(TimelineEvent.source == source)

    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.filter(TimelineEvent.event_date >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.filter(TimelineEvent.event_date <= dt_to)
        except ValueError:
            pass

    total = query.count()
    events = query.order_by(TimelineEvent.event_date.asc()).offset((page - 1) * size).limit(size).all()

    # Post-filter by tag if needed (JSON array filtering)
    if tag:
        events = [e for e in events if tag in (e.tags or [])]
        total = len(events)

    return {
        "total": total, "page": page, "size": size,
        "events": [_event_response(e, db) for e in events],
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_timeline_event(
    data: TimelineEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = TimelineEvent(
        case_id=data.case_id, title=data.title,
        description=data.description, event_date=data.event_date,
        event_end_date=data.event_end_date, location=data.location,
        material_id=data.material_id, entity_id=data.entity_id,
        source="manual", tags=data.tags,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    log_activity(db, "timeline_event_created", f"Timeline event: {data.title}",
                 user_id=current_user.id)
    return _event_response(event, db)


@router.get("/{event_id}")
def get_timeline_event(event_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Timeline event not found")
    return _event_response(event, db)


@router.put("/{event_id}")
def update_timeline_event(
    event_id: int, data: TimelineEventUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Timeline event not found")

    if data.title is not None:
        event.title = data.title
    if data.description is not None:
        event.description = data.description
    if data.event_date is not None:
        event.event_date = data.event_date
    if data.event_end_date is not None:
        event.event_end_date = data.event_end_date
    if data.location is not None:
        event.location = data.location
    if data.tags is not None:
        event.tags = data.tags

    db.commit()
    db.refresh(event)
    return _event_response(event, db)


@router.delete("/{event_id}")
def delete_timeline_event(event_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    event = db.query(TimelineEvent).filter(TimelineEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Timeline event not found")
    db.delete(event)
    db.commit()
    return {"detail": "Timeline event deleted"}


# ---- AI Generation ----

@router.post("/generate")
def generate_timeline(
    data: TimelineGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI-generate timeline events from materials and/or entities in a case."""
    key_error = llm_service.check_provider_key(data.provider)
    if key_error:
        raise HTTPException(status_code=400, detail=key_error)

    # Gather source texts
    parts = []

    # Materials
    mat_query = db.query(Material).filter(Material.case_id == data.case_id)
    if data.material_ids:
        mat_query = mat_query.filter(Material.id.in_(data.material_ids))
    materials = mat_query.all()

    for mat in materials:
        text = mat.content_text or mat.content_summary or ""
        if text:
            parts.append(f"[Document: {mat.filename}]\n{text[:8000]}")

    # Entities (especially events)
    ent_query = db.query(Entity).filter(Entity.case_id == data.case_id)
    if data.entity_ids:
        ent_query = ent_query.filter(Entity.id.in_(data.entity_ids))
    entities = ent_query.all()

    for ent in entities:
        info = f"[Entity: {ent.entity_type} - {ent.name}]"
        if ent.description:
            info += f"\n{ent.description}"
        if ent.event_date:
            info += f"\nDate: {ent.event_date}"
        if ent.event_location:
            info += f"\nLocation: {ent.event_location}"
        parts.append(info)

    if not parts:
        raise HTTPException(status_code=400, detail="No source materials or entities found")

    combined = "\n\n".join(parts)
    if len(combined) > 50000:
        combined = combined[:50000] + "\n[...truncated]"

    prompt = (
        "You are an investigative analyst building a timeline.\n"
        "From the following documents and entities, extract ALL events with dates.\n"
        "For each event provide:\n"
        "- title (short, Hebrew)\n"
        "- description (brief, Hebrew)\n"
        "- date (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)\n"
        "- end_date (if applicable, ISO format)\n"
        "- location (if known)\n"
        "- tags (comma-separated relevant labels)\n"
        "- confidence (1-100, how certain is this date)\n\n"
        "Return a JSON array of objects. Only JSON, no markdown.\n\n"
        f"Date range filter: {data.date_from or 'any'} to {data.date_to or 'any'}\n\n"
        f"{combined}"
    )

    try:
        import json
        result_text = llm_service.call_llm(prompt, provider=data.provider, max_tokens=4000)

        # Parse JSON from response
        # Try to extract JSON array from response
        result_text = result_text.strip()
        if result_text.startswith("```"):
            # Remove markdown code blocks
            lines = result_text.split("\n")
            result_text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        events_data = json.loads(result_text)
        if not isinstance(events_data, list):
            events_data = [events_data]

        created = 0
        for ev in events_data:
            try:
                event_date = datetime.fromisoformat(str(ev.get("date", "")))
            except (ValueError, TypeError):
                continue  # Skip events without valid dates

            end_date = None
            if ev.get("end_date"):
                try:
                    end_date = datetime.fromisoformat(str(ev["end_date"]))
                except (ValueError, TypeError):
                    pass

            tags = []
            if ev.get("tags"):
                if isinstance(ev["tags"], list):
                    tags = ev["tags"]
                elif isinstance(ev["tags"], str):
                    tags = [t.strip() for t in ev["tags"].split(",") if t.strip()]

            event = TimelineEvent(
                case_id=data.case_id,
                title=str(ev.get("title", ""))[:500],
                description=str(ev.get("description", ""))[:2000] if ev.get("description") else None,
                event_date=event_date,
                event_end_date=end_date,
                location=str(ev.get("location", ""))[:500] if ev.get("location") else None,
                source="ai",
                confidence=int(ev["confidence"]) if ev.get("confidence") else None,
                tags=tags,
                metadata_json={"provider": data.provider},
            )
            db.add(event)
            created += 1

        db.commit()
        log_activity(db, "timeline_generated",
                     f"Generated {created} timeline events from {len(materials)} docs",
                     user_id=current_user.id)

        return {"created": created, "source_materials": len(materials), "source_entities": len(entities)}

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="AI returned invalid JSON. Try again or use a different provider.")
    except Exception as e:
        logger.error("Timeline generation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)[:200]}")
