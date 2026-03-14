"""Lightweight schema migrations — runs on every startup.

Each migration checks whether it has already been applied before modifying
the schema, so they are safe to re-run.
"""

import logging
from sqlalchemy import text as sa_text, inspect
from app.database import SessionLocal, engine

logger = logging.getLogger("case-dms.migrations")


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    columns = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in columns


def run_migrations():
    """Execute all idempotent schema migrations."""
    inspector = inspect(engine)
    db = SessionLocal()

    try:
        # Migration 1: Add extraction_error to materials (if missing)
        if _table_exists(inspector, "materials") and not _column_exists(inspector, "materials", "extraction_error"):
            db.execute(sa_text("ALTER TABLE materials ADD COLUMN extraction_error TEXT"))
            db.commit()
            logger.info("Migration: added materials.extraction_error")

        # Migration 2: Add user_agent to activity_log (if missing)
        if _table_exists(inspector, "activity_log") and not _column_exists(inspector, "activity_log", "user_agent"):
            db.execute(sa_text("ALTER TABLE activity_log ADD COLUMN user_agent VARCHAR(200)"))
            db.commit()
            logger.info("Migration: added activity_log.user_agent")

        # Migration 3: Add about_approved_at/version to users (if missing)
        if _table_exists(inspector, "users") and not _column_exists(inspector, "users", "about_approved_at"):
            db.execute(sa_text("ALTER TABLE users ADD COLUMN about_approved_at TIMESTAMP"))
            db.commit()
            logger.info("Migration: added users.about_approved_at")

        if _table_exists(inspector, "users") and not _column_exists(inspector, "users", "about_approved_version"):
            db.execute(sa_text("ALTER TABLE users ADD COLUMN about_approved_version INTEGER"))
            db.commit()
            logger.info("Migration: added users.about_approved_version")

        logger.info("Migrations: complete")

    except Exception as e:
        db.rollback()
        logger.error("Migration failed: %s", e, exc_info=True)
    finally:
        db.close()
