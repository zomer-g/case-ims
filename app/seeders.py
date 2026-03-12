"""Initial seed data — runs on every startup, idempotently."""

import logging
from app.database import SessionLocal
from app.models import PromptRule, SiteSetting

logger = logging.getLogger("case-ims.seeders")


def run_seeders():
    db = SessionLocal()
    try:
        _seed_base_prompt(db)
        _seed_site_settings(db)
        logger.info("Seeders: complete")
    except Exception as e:
        db.rollback()
        logger.error("Seeder failed: %s", e, exc_info=True)
    finally:
        db.close()


def _seed_base_prompt(db):
    """Create the default base prompt rule if none exist."""
    if db.query(PromptRule).count() > 0:
        return

    base_prompt = PromptRule(
        name="base",
        trigger_tag=None,
        trigger_value=None,
        prompt_text=(
            "אתה מנתח חומרי חקירה מקצועי. קבל את תוכן המסמך הבא ומלא את שדות ה-JSON.\n"
            "הנחיות:\n"
            "- ענה אך ורק ב-JSON תקין\n"
            "- אם שדה לא רלוונטי, השאר מחרוזת ריקה\n"
            "- כתוב בעברית\n\n"
            "שדות נדרשים:\n"
            "{\n"
            '  "סוג_מסמך": "",\n'
            '  "תקציר": "",\n'
            '  "תאריך": "",\n'
            '  "גורמים_מעורבים": [],\n'
            '  "מילות_מפתח": [],\n'
            '  "מיקום": "",\n'
            '  "רמת_רלוונטיות": ""\n'
            "}"
        ),
        is_active=True,
        json_schema=None,
        max_tokens=3000,
    )
    db.add(base_prompt)
    db.commit()
    logger.info("Seeded base prompt rule")


def _seed_site_settings(db):
    """Seed default site settings if they don't exist."""
    defaults = {
        "app_title": "Case-IMS",
        "app_subtitle": "מערכת ניהול חומרי חקירה",
    }
    for key, value in defaults.items():
        existing = db.query(SiteSetting).filter(SiteSetting.key == key).first()
        if not existing:
            db.add(SiteSetting(key=key, value=value))
    db.commit()
