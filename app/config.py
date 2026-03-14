import secrets
from pydantic_settings import BaseSettings
from typing import Optional, Set


def _generate_secret() -> str:
    return secrets.token_hex(32)


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///./dms.db"

    # JWT
    SECRET_KEY: str = _generate_secret()
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # App
    APP_NAME: str = "Case-DMS"
    DEBUG: bool = False
    UPLOAD_DIR: str = "uploads"

    # CORS
    ALLOWED_ORIGINS: str = ""

    # Security
    MAX_UPLOAD_SIZE_MB: int = 100

    # Timezone
    APP_TIMEZONE: str = "Asia/Jerusalem"

    # AI / LLM
    DEEPSEEK_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_CLIENT_ID: Optional[str] = None

    # Processing
    MAX_TEXT_LENGTH: int = 200_000
    MAX_TRIGGER_DEPTH: int = 10

    # Admin
    ADMIN_EMAILS: Optional[str] = None

    # Runtime mode: "local" or "cloud"
    RUNTIME_MODE: str = "cloud"
    LOCAL_WATCH_PATHS: Optional[str] = None
    SCAN_INTERVAL_MINUTES: int = 15

    # Media processing
    WHISPER_API_URL: Optional[str] = None
    WHISPER_MODEL: str = "whisper-1"
    VISION_PROVIDER: str = "gemini"
    MAX_AUDIO_CHUNK_MB: int = 25
    VIDEO_FRAME_INTERVAL: int = 30
    THUMBNAIL_WIDTH: int = 400

    # Bridge API (future)
    BRIDGE_API_KEY: Optional[str] = None
    SMART_DMS_URL: Optional[str] = None
    SMART_DMS_BRIDGE_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True

    def get_admin_emails(self) -> Set[str]:
        if not self.ADMIN_EMAILS:
            return set()
        return {e.strip().lower() for e in self.ADMIN_EMAILS.split(",") if e.strip()}

    def get_allowed_origins(self) -> list[str]:
        if self.ALLOWED_ORIGINS:
            return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]
        if self.DEBUG:
            return ["*"]
        return []


settings = Settings()

import threading as _threading
_tz_lock = _threading.Lock()
_runtime_timezone: str = settings.APP_TIMEZONE


def get_timezone() -> str:
    with _tz_lock:
        return _runtime_timezone


def set_timezone(tz: str) -> None:
    global _runtime_timezone
    with _tz_lock:
        _runtime_timezone = tz
