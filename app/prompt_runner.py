"""
prompt_runner.py — Prompt management and execution for Case-IMS.
Allows creating reusable prompts and running them against selected materials.
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.auth import get_current_user
from app import models, llm_service

logger = logging.getLogger("case-ims.prompts")

router = APIRouter(prefix="/prompts", tags=["Prompts"])


# ---- Schemas ----

class PromptCreate(BaseModel):
    name: str
    prompt_text: str
    case_id: Optional[int] = None
    is_active: bool = True
    max_tokens: int = 2000
    json_schema: Optional[str] = None


class PromptUpdate(BaseModel):
    name: Optional[str] = None
    prompt_text: Optional[str] = None
    case_id: Optional[int] = None
    is_active: Optional[bool] = None
    max_tokens: Optional[int] = None
    json_schema: Optional[str] = None


class PromptRunRequest(BaseModel):
    material_ids: List[int]
    provider: str = "gemini"


class PromptRunCustomRequest(BaseModel):
    material_ids: List[int]
    prompt_text: str
    provider: str = "gemini"
    max_tokens: int = 4000


# ---- CRUD ----

@router.get("/")
def list_prompts(
    case_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.PromptRule)
    if case_id is not None:
        from sqlalchemy import or_
        query = query.filter(or_(
            models.PromptRule.case_id == case_id,
            models.PromptRule.case_id.is_(None),
        ))
    prompts = query.order_by(models.PromptRule.name).all()
    return {
        "prompts": [
            {
                "id": p.id, "name": p.name, "prompt_text": p.prompt_text,
                "case_id": p.case_id, "case_name": p.case_name,
                "is_active": p.is_active, "max_tokens": p.max_tokens,
                "json_schema": p.json_schema,
            }
            for p in prompts
        ]
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_prompt(
    data: PromptCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not data.name.strip() or not data.prompt_text.strip():
        raise HTTPException(status_code=400, detail="name and prompt_text required")

    prompt = models.PromptRule(
        name=data.name.strip(),
        prompt_text=data.prompt_text.strip(),
        case_id=data.case_id,
        is_active=data.is_active,
        max_tokens=data.max_tokens,
        json_schema=data.json_schema,
    )
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return {"id": prompt.id, "name": prompt.name}


@router.put("/{prompt_id}")
def update_prompt(
    prompt_id: int,
    data: PromptUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    prompt = db.query(models.PromptRule).filter(models.PromptRule.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    if data.name is not None:
        prompt.name = data.name.strip()
    if data.prompt_text is not None:
        prompt.prompt_text = data.prompt_text.strip()
    if data.case_id is not None:
        prompt.case_id = data.case_id
    if data.is_active is not None:
        prompt.is_active = data.is_active
    if data.max_tokens is not None:
        prompt.max_tokens = data.max_tokens
    if data.json_schema is not None:
        prompt.json_schema = data.json_schema

    db.commit()
    return {"id": prompt.id, "updated": True}


@router.delete("/{prompt_id}")
def delete_prompt(
    prompt_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    prompt = db.query(models.PromptRule).filter(models.PromptRule.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    db.delete(prompt)
    db.commit()
    return {"deleted": True}


# ---- Run Prompts ----

def _gather_material_texts(db: Session, material_ids: List[int], max_per_doc: int = 10000, max_total: int = 50000) -> str:
    """Gather and concatenate material texts for LLM processing."""
    texts = []
    total_len = 0
    for mid in material_ids:
        mat = db.query(models.Material).filter(models.Material.id == mid).first()
        if not mat or not mat.content_text:
            continue
        text = mat.content_text[:max_per_doc]
        if total_len + len(text) > max_total:
            text = text[:max_total - total_len]
        texts.append(f"=== {mat.filename} (ID: {mat.id}) ===\n{text}")
        total_len += len(text)
        if total_len >= max_total:
            break
    return "\n\n".join(texts)


@router.post("/{prompt_id}/run")
def run_prompt(
    prompt_id: int,
    data: PromptRunRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Run a saved prompt against selected materials."""
    prompt = db.query(models.PromptRule).filter(models.PromptRule.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    if not data.material_ids:
        raise HTTPException(status_code=400, detail="material_ids required")

    key_error = llm_service.check_provider_key(data.provider)
    if key_error:
        raise HTTPException(status_code=400, detail=key_error)

    combined_text = _gather_material_texts(db, data.material_ids)
    if not combined_text:
        raise HTTPException(status_code=400, detail="No text content found in selected materials")

    try:
        result = llm_service.analyze_text(
            text=combined_text,
            prompt=prompt.prompt_text,
            json_schema=prompt.json_schema,
            max_tokens=prompt.max_tokens,
            provider=data.provider,
        )
        return {"result": result, "material_count": len(data.material_ids), "prompt_name": prompt.name}
    except Exception as e:
        logger.error("Prompt run failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-custom")
def run_custom_prompt(
    data: PromptRunCustomRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Run an ad-hoc prompt against selected materials."""
    if not data.material_ids or not data.prompt_text.strip():
        raise HTTPException(status_code=400, detail="material_ids and prompt_text required")

    key_error = llm_service.check_provider_key(data.provider)
    if key_error:
        raise HTTPException(status_code=400, detail=key_error)

    combined_text = _gather_material_texts(db, data.material_ids)
    if not combined_text:
        raise HTTPException(status_code=400, detail="No text content found in selected materials")

    try:
        result = llm_service.analyze_text(
            text=combined_text,
            prompt=data.prompt_text.strip(),
            max_tokens=data.max_tokens,
            provider=data.provider,
        )
        return {"result": result, "material_count": len(data.material_ids)}
    except Exception as e:
        logger.error("Custom prompt run failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
