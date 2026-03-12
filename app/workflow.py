"""AI analysis workflow: base prompt -> recursive triggers -> auto-field discovery."""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from app import llm_service
from app.models import PromptRule, DetectedField
from app.config import settings
from app.field_utils import classify_value as _classify_value

logger = logging.getLogger("case-ims.workflow")

MAX_TRIGGER_DEPTH = settings.MAX_TRIGGER_DEPTH


def _extract_keys(data: object, prefix: str = "") -> set[str]:
    keys = set()
    if isinstance(data, dict):
        for k, v in data.items():
            full_key = f"{prefix}.{k}" if prefix else k
            keys.add(full_key)
            keys |= _extract_keys(v, full_key)
    elif isinstance(data, list):
        for item in data:
            keys |= _extract_keys(item, prefix)
    return keys


def _resolve_nested_value(data: object, dot_key: str) -> object:
    parts = dot_key.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and current:
            first = current[0]
            if isinstance(first, dict) and part in first:
                current = first[part]
            else:
                return None
        else:
            return None
    return current


def upsert_detected_fields(data: dict, db: Session):
    try:
        keys = _extract_keys(data)
        if not keys:
            return
        existing = {row.field_key for row in db.query(DetectedField.field_key).all()}
        new_keys = keys - existing
        if new_keys:
            for k in sorted(new_keys):
                val = _resolve_nested_value(data, k)
                ft, is_arr = _classify_value(val)
                db.add(DetectedField(field_key=k, field_type=ft, is_array=is_arr))
            db.commit()
            logger.info("Auto-discovered %d new field(s): %s", len(new_keys), sorted(new_keys))
    except Exception as e:
        logger.error("Failed to upsert detected fields: %s", e)
        db.rollback()


class _MissingSentinel:
    def __repr__(self):
        return "<MISSING>"

_MISSING = _MissingSentinel()


def _resolve_key(data: dict, dot_path: str):
    parts = dot_path.split(".")
    current = data
    for i, part in enumerate(parts):
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                return _MISSING
        elif isinstance(current, list):
            remaining = ".".join(parts[i:])
            collected = []
            for item in current:
                val = _resolve_key(item, remaining) if isinstance(item, dict) else _MISSING
                if val is not _MISSING:
                    if isinstance(val, list):
                        collected.extend(val)
                    else:
                        collected.append(val)
            return collected if collected else _MISSING
        else:
            return _MISSING
    return current


def _value_matches(actual_value, trigger_value: str) -> bool:
    if actual_value is _MISSING:
        return False
    tv_lower = trigger_value.strip().lower()
    if isinstance(actual_value, list):
        for item in actual_value:
            if isinstance(item, str) and item.strip().lower() == tv_lower:
                return True
            elif str(item).strip().lower() == tv_lower:
                return True
        return False
    if isinstance(actual_value, str):
        return actual_value.strip().lower() == tv_lower
    return str(actual_value).strip().lower() == tv_lower


def _find_matching_rules(data: dict, rules: list[PromptRule], already_fired: set) -> list[PromptRule]:
    matched = []
    for rule in rules:
        if rule.id in already_fired:
            continue
        actual = _resolve_key(data, rule.trigger_tag)
        if _value_matches(actual, rule.trigger_value):
            matched.append(rule)
    return matched


def run_material_workflow(
    material_id: int, text: str, db: Session,
    provider: str = llm_service.DEFAULT_PROVIDER,
    case_id: Optional[int] = None
) -> dict:
    """Dynamic AI workflow for investigative materials."""
    if not text or not text.strip():
        return {"summary": "", "tags": [], "error": "No text to analyze"}

    # Step 1: Base classification
    base_rule = (
        db.query(PromptRule)
        .filter(PromptRule.trigger_tag.is_(None), PromptRule.is_active.is_(True))
        .first()
    )

    if not base_rule:
        logger.warning("No active base prompt rule found for material %d", material_id)
        return {"summary": "", "tags": [], "error": "No base prompt configured"}

    try:
        logger.info("Step 1 - base rule '%s' for material %d (provider=%s)", base_rule.name, material_id, provider)
        classification = llm_service.analyze_text(
            text, base_rule.prompt_text,
            json_schema=base_rule.json_schema, max_tokens=base_rule.max_tokens, provider=provider,
        )
        upsert_detected_fields(classification, db)
    except Exception as e:
        logger.error("Step 1 failed for material %d: %s", material_id, e)
        return {"summary": "Error analyzing material", "tags": [], "error": str(e)}

    result = dict(classification)
    extra_analysis = {}
    fired_ids = set()

    # Step 2a: Case-based rules
    if case_id is not None:
        case_rules = (
            db.query(PromptRule)
            .filter(PromptRule.case_id == case_id, PromptRule.is_active.is_(True))
            .all()
        )
        for rule in case_rules:
            fired_ids.add(rule.id)
            try:
                extra = llm_service.analyze_text(
                    text, rule.prompt_text,
                    json_schema=rule.json_schema, max_tokens=rule.max_tokens, provider=provider,
                )
                upsert_detected_fields(extra, db)
                extra_analysis[rule.name] = extra
            except Exception as e:
                logger.error("Case rule '%s' failed for material %d: %s", rule.name, material_id, e)

    # Step 2b: Chained triggers
    kv_rules = (
        db.query(PromptRule)
        .filter(
            PromptRule.trigger_tag.isnot(None),
            PromptRule.trigger_value.isnot(None),
            PromptRule.case_id.is_(None),
            PromptRule.is_active.is_(True),
        )
        .all()
    )

    if kv_rules:
        depth = 0
        while depth < MAX_TRIGGER_DEPTH:
            depth += 1
            combined = dict(result)
            for rule_name, rule_data in extra_analysis.items():
                if isinstance(rule_data, dict):
                    combined.update(rule_data)

            matched = _find_matching_rules(combined, kv_rules, fired_ids)
            if not matched:
                break

            for rule in matched:
                fired_ids.add(rule.id)
                try:
                    extra = llm_service.analyze_text(
                        text, rule.prompt_text,
                        json_schema=rule.json_schema, max_tokens=rule.max_tokens, provider=provider,
                    )
                    upsert_detected_fields(extra, db)
                    extra_analysis[rule.name] = extra
                except Exception as e:
                    logger.error("Trigger rule '%s' failed for material %d: %s", rule.name, material_id, e)

    if extra_analysis:
        result["extra_analysis"] = extra_analysis

    # Audit trail
    result["_model_used"] = {
        "provider": provider,
        "model": llm_service.get_model_display_name(provider),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return result
