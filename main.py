import os
import logging
import warnings

# ---- Suppress noisy third-party warnings (pydub/ffmpeg from markitdown) ----
warnings.filterwarnings("ignore", message=".*pydub.*", category=RuntimeWarning)
warnings.filterwarnings("ignore", message=".*ffmpeg.*", category=RuntimeWarning)
warnings.filterwarnings("ignore", message=".*ffprobe.*", category=RuntimeWarning)

# ---- Configure application logging to match Uvicorn format ----
_log_formatter = logging.Formatter(
    "%(levelname)s:     %(name)s - %(message)s"
)
_log_handler = logging.StreamHandler()
_log_handler.setFormatter(_log_formatter)

_app_logger = logging.getLogger("case-ims")
_app_logger.setLevel(logging.DEBUG if os.getenv("DEBUG", "False").lower() == "true" else logging.INFO)
_app_logger.addHandler(_log_handler)
_app_logger.propagate = False

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base, SessionLocal
from app import auth, users, materials, cases, queue as queue_module
from app import admin, admin_prompts, admin_fields, admin_system
from app import entities, folders, groups, timeline, prompt_runner
from app.config import settings
from app.models import User, SiteSetting

logger = logging.getLogger("case-ims")

# Create database tables
Base.metadata.create_all(bind=engine)

# Run lightweight schema migrations + seed data
from app.migrations import run_migrations
from app.seeders import run_seeders

run_migrations()
run_seeders()

# Initialize FastAPI app — disable Swagger UI in production
app = FastAPI(
    title=settings.APP_NAME,
    description="An Investigative Materials System API",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# ---- Rate Limiting (slowapi) ----
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS — restricted origins in production
_allowed_origins = settings.get_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=bool(_allowed_origins and _allowed_origins != ["*"]),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
if _allowed_origins == ["*"]:
    logger.warning("CORS: allow_origins=['*'] — set ALLOWED_ORIGINS in production!")

# Security headers + static file cache control
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if not settings.DEBUG:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://accounts.google.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://accounts.google.com; "
                "font-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "img-src 'self' data: https:; "
                "frame-src 'self' https://accounts.google.com; "
                "connect-src 'self' https://accounts.google.com"
            )
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# Include API routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(materials.router)
app.include_router(cases.router)
app.include_router(admin.router)
app.include_router(admin_prompts.router)
app.include_router(admin_fields.router)
app.include_router(admin_system.router)
app.include_router(queue_module.router)
app.include_router(entities.router)
app.include_router(folders.router)
app.include_router(groups.router)
app.include_router(timeline.router)
app.include_router(prompt_runner.router)


# ---- Queue Worker Startup ----
@app.on_event("startup")
def start_queue():
    """Reset any stale 'running' jobs (crash recovery) and start the queue worker thread."""
    from app.queue_processor import reset_stale_jobs, start_queue_worker
    reset_stale_jobs()
    start_queue_worker()


# ---- Admin Promotion on Startup ----
@app.on_event("startup")
def promote_admin_emails():
    """For every email in ADMIN_EMAILS that already exists in the DB,
    force is_admin=True."""
    admin_emails = settings.get_admin_emails()
    if not admin_emails:
        return

    db = SessionLocal()
    promoted = []
    try:
        for email in admin_emails:
            user = db.query(User).filter(User.email == email).first()
            if user and not user.is_admin:
                user.is_admin = True
                db.add(user)
                promoted.append(email)
        if promoted:
            db.commit()
            for email in promoted:
                logger.info("Startup: promoted %s to ADMIN", email)
    except Exception as exc:
        db.rollback()
        logger.error("Admin promotion failed: %s", exc, exc_info=True)
    finally:
        db.close()


# ---- Public Site Settings API ----
from sqlalchemy.orm import Session
from app.database import get_db


@app.get("/api/site-settings/{key}")
def get_site_setting(key: str, db: Session = Depends(get_db)):
    """Public endpoint — returns a site setting value (no auth required)."""
    setting = db.query(SiteSetting).filter(SiteSetting.key == key).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    return {"key": setting.key, "value": setting.value}


# Mount static files (frontend) - MUST come after API routers
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    """Redirect root to the frontend"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


@app.get("/health")
def health_check():
    """Health check endpoint — minimal info only (no paths, no DB URLs)."""
    info = {"status": "healthy"}
    try:
        from app.database import SessionLocal as _HealthSL
        _hdb = _HealthSL()
        try:
            from app.models import User as _HUser
            info["db_ok"] = _hdb.query(_HUser).count() >= 0
        except Exception:
            info["db_ok"] = False
        finally:
            _hdb.close()
    except Exception:
        info["db_ok"] = False
    return info


# ---- Timezone settings ----

@app.get("/settings/timezone")
def get_app_timezone():
    """Return the current app timezone. Public (no auth)."""
    from app.config import get_timezone
    return {"timezone": get_timezone()}


@app.put("/settings/timezone")
def set_app_timezone(
    body: dict,
    current_admin: User = Depends(auth.get_current_admin_user),
):
    """Update the app timezone (admin only). Body: {"timezone": "Asia/Jerusalem"}"""
    import zoneinfo
    tz = body.get("timezone", "").strip()
    if not tz:
        raise HTTPException(status_code=400, detail="timezone is required")
    try:
        zoneinfo.ZoneInfo(tz)
    except (KeyError, Exception):
        raise HTTPException(status_code=400, detail=f"Invalid timezone: {tz}")
    from app.config import set_timezone
    set_timezone(tz)
    logger.info("Timezone updated to '%s' by admin %s", tz, current_admin.email)
    return {"timezone": tz}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
