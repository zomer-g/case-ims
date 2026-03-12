"""Singleton background worker thread for serialized material processing."""

import gc
import os
import threading
import logging
import time
from datetime import datetime, timezone
from sqlalchemy.orm.attributes import flag_modified
from app.database import SessionLocal, get_session
from app import models

logger = logging.getLogger("case-ims.queue")

_worker_thread: threading.Thread | None = None
_stop_event = threading.Event()

MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 45]


def _log_memory():
    try:
        import psutil
        rss_mb = psutil.Process().memory_info().rss / (1024 * 1024)
        logger.info("Queue: RSS memory = %.1f MB", rss_mb)
    except ImportError:
        try:
            import resource
            rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
            logger.info("Queue: RSS memory = %.1f MB", rss_mb)
        except ImportError:
            pass
    except Exception:
        pass


def _worker_loop():
    logger.info("Queue worker started")
    idle_count = 0
    while not _stop_event.is_set():
        had_work = _process_one()
        if not had_work:
            idle_count += 1
            if idle_count % 60 == 0:
                _log_memory()
            _stop_event.wait(timeout=1.0)
        else:
            idle_count = 0


def _process_one() -> bool:
    from app.materials import background_ai_task
    from app.extractors import convert_to_markdown

    db = SessionLocal()
    try:
        item = (
            db.query(models.ProcessingQueue)
            .filter(models.ProcessingQueue.status == "pending")
            .order_by(
                models.ProcessingQueue.priority.asc(),
                models.ProcessingQueue.queued_at.asc(),
            )
            .first()
        )
        if item is None:
            return False

        mat = db.query(models.Material).filter(models.Material.id == item.material_id).first()
        if mat is None:
            item.status = "failed"
            item.error_detail = "Material deleted before processing"
            item.finished_at = datetime.now(timezone.utc)
            db.commit()
            return True

        item.status = "running"
        item.started_at = datetime.now(timezone.utc)
        db.commit()

        item_id = item.id
        mat_id = item.material_id
        provider = item.provider
        file_path = mat.file_path

        # Step 1: Text extraction
        text = mat.content_text or ""
        if not text.strip() and os.path.exists(file_path):
            logger.info("Queue: extracting text for material %d (%s)", mat_id, mat.filename)
            try:
                text = convert_to_markdown(file_path)
                if text.strip():
                    md_path = f"{file_path}.md"
                    try:
                        with open(md_path, "w", encoding="utf-8") as f:
                            f.write(text)
                    except Exception as e:
                        logger.error("Queue: .md sidecar write failed: %s", e)
                mat.content_text = text
                mat.extraction_status = "done"
                flag_modified(mat, "content_text")
                db.commit()
            except Exception as e:
                logger.error("Queue: text extraction failed for material %d: %s", mat_id, e)
                text = ""
                mat.extraction_status = "failed"
                mat.extraction_error = str(e)[:500]
                db.commit()

    except Exception as e:
        logger.error("Queue: error claiming item: %s", e)
        db.rollback()
        return False
    finally:
        db.close()

    # Step 2: AI analysis
    if not text.strip():
        logger.info("Queue: no text for material %d, skipping AI", mat_id)
        _mark_done(item_id)
        return True

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            if attempt > 0:
                delay = RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)]
                logger.info("Queue: job %d retry %d/%d after %ds", item_id, attempt, MAX_RETRIES, delay)
                time.sleep(delay)
            logger.info("Queue: processing job %d (material=%d, provider=%s, attempt=%d)", item_id, mat_id, provider, attempt + 1)
            background_ai_task(mat_id, text, file_path, provider)
            _mark_done(item_id)
            last_error = None
            break
        except Exception as e:
            last_error = e
            logger.warning("Queue: job %d attempt %d failed: %s", item_id, attempt + 1, e)

    if last_error is not None:
        logger.error("Queue: job %d failed after %d attempts: %s", item_id, MAX_RETRIES + 1, last_error)
        _mark_failed(item_id, str(last_error))

    gc.collect()
    _log_memory()
    return True


def _mark_done(item_id: int):
    with get_session() as db:
        try:
            item = db.query(models.ProcessingQueue).filter(models.ProcessingQueue.id == item_id).first()
            if item:
                item.status = "done"
                item.finished_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as e:
            logger.error("Queue: _mark_done failed: %s", e)
            db.rollback()


def _mark_failed(item_id: int, error: str):
    with get_session() as db:
        try:
            item = db.query(models.ProcessingQueue).filter(models.ProcessingQueue.id == item_id).first()
            if item:
                item.status = "failed"
                item.error_detail = (error or "Unknown error")[:1000]
                item.finished_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as e:
            logger.error("Queue: _mark_failed failed: %s", e)
            db.rollback()


def start_queue_worker():
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        logger.info("Queue worker already running")
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(target=_worker_loop, name="queue-worker", daemon=True)
    _worker_thread.start()
    logger.info("Queue worker thread launched")


def reset_stale_jobs():
    with get_session() as db:
        try:
            stale = db.query(models.ProcessingQueue).filter(models.ProcessingQueue.status == "running").all()
            for item in stale:
                item.status = "pending"
                item.started_at = None
                logger.info("Queue: reset stale running job %d", item.id)
            if stale:
                db.commit()
        except Exception as e:
            logger.error("Queue: reset_stale_jobs failed: %s", e)
            db.rollback()
