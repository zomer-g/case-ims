"""Admin prompt rule management."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_admin_user
from app.models import PromptRule, User

logger = logging.getLogger("case-ims.admin-prompts")

router = APIRouter(prefix="/admin/prompts", tags=["Admin – Prompts"])


@router.get("/")
def list_prompts(db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    rules = db.query(PromptRule).order_by(PromptRule.id).all()
    return [
        {
            "id": r.id, "name": r.name,
            "trigger_tag": r.trigger_tag, "trigger_value": r.trigger_value,
            "prompt_text": r.prompt_text, "is_active": r.is_active,
            "json_schema": r.json_schema, "max_tokens": r.max_tokens,
            "case_id": r.case_id, "case_name": r.case_name,
        }
        for r in rules
    ]


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_prompt(data: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    if not data.get("name") or not data.get("prompt_text"):
        raise HTTPException(status_code=400, detail="name and prompt_text required")

    existing = db.query(PromptRule).filter(PromptRule.name == data["name"]).first()
    if existing:
        raise HTTPException(status_code=400, detail="Prompt name already exists")

    rule = PromptRule(
        name=data["name"],
        trigger_tag=data.get("trigger_tag"),
        trigger_value=data.get("trigger_value"),
        prompt_text=data["prompt_text"],
        is_active=data.get("is_active", True),
        json_schema=data.get("json_schema"),
        max_tokens=data.get("max_tokens", 2000),
        case_id=data.get("case_id"),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"id": rule.id, "name": rule.name, "created": True}


@router.put("/{rule_id}")
def update_prompt(rule_id: int, data: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    rule = db.query(PromptRule).filter(PromptRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Prompt rule not found")

    for field in ("name", "trigger_tag", "trigger_value", "prompt_text", "is_active", "json_schema", "max_tokens", "case_id"):
        if field in data:
            setattr(rule, field, data[field])

    db.commit()
    return {"id": rule.id, "updated": True}


@router.delete("/{rule_id}")
def delete_prompt(rule_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    rule = db.query(PromptRule).filter(PromptRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Prompt rule not found")
    db.delete(rule)
    db.commit()
    return {"detail": "Prompt rule deleted"}
