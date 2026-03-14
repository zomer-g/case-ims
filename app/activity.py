"""Persistent activity logging helper."""

import logging
from sqlalchemy.orm import Session
from app.models import ActivityLog

logger = logging.getLogger("case-dms.activity")


def _parse_ua(raw: str) -> str:
    if not raw:
        return ""
    r = raw.lower()

    if "iphone" in r:
        device = "iPhone"
    elif "ipad" in r:
        device = "iPad"
    elif "android" in r:
        device = "Android"
    elif "windows" in r:
        device = "Windows"
    elif "mac os" in r or "macintosh" in r:
        device = "Mac"
    elif "linux" in r:
        device = "Linux"
    else:
        device = ""

    if "edg/" in r or "edge/" in r:
        browser = "Edge"
    elif "chrome/" in r and "chromium" not in r:
        browser = "Chrome"
    elif "firefox/" in r:
        browser = "Firefox"
    elif "safari/" in r:
        browser = "Safari"
    elif "opr/" in r or "opera" in r:
        browser = "Opera"
    else:
        browser = ""

    if browser and device:
        return f"{browser} / {device}"
    elif browser:
        return browser
    elif device:
        return device
    else:
        return raw[:80]


def log_activity(
    db: Session,
    event_type: str,
    detail: str = "",
    user_id: int = None,
    material_id: int = None,
    level: str = "info",
    commit: bool = True,
    user_agent: str = None,
):
    try:
        entry = ActivityLog(
            event_type=event_type,
            detail=detail,
            user_id=user_id,
            material_id=material_id,
            level=level,
            user_agent=user_agent,
        )
        db.add(entry)
        if commit:
            db.commit()
        else:
            db.flush()
        logger.debug("Activity logged: %s (user=%s, material=%s)", event_type, user_id, material_id)
    except Exception as e:
        logger.error("Failed to log activity: %s", e, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
