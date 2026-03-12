import re
import calendar
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, Set
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

logger = logging.getLogger("case-ims.auth")
from app.database import get_db
from app.models import User, Material, Feedback, SiteSetting
from app.schemas import TokenData, UserCreate, UserResponse, Token, ChangePasswordRequest, GoogleAuthRequest, FeedbackCreate
from app.activity import log_activity, _parse_ua

limiter = Limiter(key_func=get_remote_address)

# Token blocklist
_revoked_jtis: Set[str] = set()
_revoked_lock = threading.Lock()


def revoke_token(jti: str) -> None:
    with _revoked_lock:
        _revoked_jtis.add(jti)


def is_token_revoked(jti: str) -> bool:
    with _revoked_lock:
        return jti in _revoked_jtis


# Password strength
MIN_PASSWORD_LENGTH = 8

def _validate_password_strength(password: str) -> Optional[str]:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"\u05d4\u05e1\u05d9\u05e1\u05de\u05d4 \u05d7\u05d9\u05d9\u05d1\u05ea \u05dc\u05d4\u05db\u05d9\u05dc \u05dc\u05e4\u05d7\u05d5\u05ea {MIN_PASSWORD_LENGTH} \u05ea\u05d5\u05d5\u05d9\u05dd"
    if not re.search(r"[A-Za-z]", password):
        return "\u05d4\u05e1\u05d9\u05e1\u05de\u05d4 \u05d7\u05d9\u05d9\u05d1\u05ea \u05dc\u05d4\u05db\u05d9\u05dc \u05dc\u05e4\u05d7\u05d5\u05ea \u05d0\u05d5\u05ea \u05d0\u05d7\u05ea \u05d1\u05d0\u05e0\u05d2\u05dc\u05d9\u05ea"
    if not re.search(r"\d", password):
        return "\u05d4\u05e1\u05d9\u05e1\u05de\u05d4 \u05d7\u05d9\u05d9\u05d1\u05ea \u05dc\u05d4\u05db\u05d9\u05dc \u05dc\u05e4\u05d7\u05d5\u05ea \u05e1\u05e4\u05e8\u05d4 \u05d0\u05d7\u05ea"
    return None


pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    import uuid
    to_encode = data.copy()
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now, "jti": str(uuid.uuid4())})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


VIEW_TOKEN_EXPIRE_MINUTES = 5

def create_view_token(email: str, material_id: int) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": email,
        "material_id": material_id,
        "purpose": "material_view",
        "exp": now + timedelta(minutes=VIEW_TOKEN_EXPIRE_MINUTES),
        "iat": now,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    if not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
        jti = payload.get("jti")
        if jti and is_token_revoked(jti):
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.email == token_data.email).first()
    if user is None:
        raise credentials_exception

    pw_changed = getattr(user, "password_changed_at", None)
    if pw_changed:
        iat = payload.get("iat")
        if iat:
            pw_changed_ts = calendar.timegm(pw_changed.utctimetuple())
            if iat < pw_changed_ts:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token expired due to password change",
                    headers={"WWW-Authenticate": "Bearer"},
                )
    return user


async def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db)
) -> Optional[User]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            return None
        jti = payload.get("jti")
        if jti and is_token_revoked(jti):
            return None
    except JWTError:
        return None
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    pw_changed = getattr(user, "password_changed_at", None)
    if pw_changed:
        iat = payload.get("iat")
        if iat:
            pw_changed_ts = calendar.timegm(pw_changed.utctimetuple())
            if iat < pw_changed_ts:
                return None
    return user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user


# ===== ENDPOINTS =====

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
def register(request: Request, user_data: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    pw_error = _validate_password_strength(user_data.password)
    if pw_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=pw_error)

    admin_emails = settings.get_admin_emails()
    is_admin = user_data.email.strip().lower() in admin_emails

    default_max = 0
    try:
        dmu_setting = db.query(SiteSetting).filter(SiteSetting.key == "default_max_upload_docs").first()
        if dmu_setting and dmu_setting.value:
            default_max = int(dmu_setting.value)
    except Exception:
        pass

    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        email=user_data.email,
        password_hash=hashed_password,
        is_admin=is_admin,
        max_upload_docs=default_max,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    if is_admin:
        logger.info("Auto-promoted %s to ADMIN (matched ADMIN_EMAILS)", user_data.email)

    log_activity(db, "register", f"New user registered: {new_user.email}", user_id=new_user.id,
                 user_agent=_parse_ua(request.headers.get("user-agent", "")))

    return {
        "email": new_user.email, "id": new_user.id, "is_admin": new_user.is_admin,
        "auth_provider": new_user.auth_provider or "local", "created_at": new_user.created_at,
        "max_upload_docs": new_user.max_upload_docs or 0,
        "default_visibility": new_user.default_visibility or "private",
        "about_approved_at": new_user.about_approved_at,
        "about_approved_version": new_user.about_approved_version,
        "needs_about_approval": True, "material_count": 0,
    }


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)
    log_activity(db, "login", f"User logged in: {user.email}", user_id=user.id,
                 user_agent=_parse_ua(request.headers.get("user-agent", "")))
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        raw_token = auth_header[7:]
        try:
            payload = jwt.decode(raw_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            jti = payload.get("jti")
            if jti:
                revoke_token(jti)
        except JWTError:
            pass
    log_activity(db, "logout", f"User logged out: {current_user.email}", user_id=current_user.id)
    return {"detail": "Logged out successfully"}


@router.post("/change-password", response_model=UserResponse)
def change_password(data: ChangePasswordRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.auth_provider == "google":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="\u05de\u05e9\u05ea\u05de\u05e9\u05d9 Google SSO \u05dc\u05d0 \u05d9\u05db\u05d5\u05dc\u05d9\u05dd \u05dc\u05e9\u05e0\u05d5\u05ea \u05e1\u05d9\u05e1\u05de\u05d4")
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="\u05e1\u05d9\u05e1\u05de\u05d4 \u05e0\u05d5\u05db\u05d7\u05d9\u05ea \u05e9\u05d2\u05d5\u05d9\u05d4")
    pw_error = _validate_password_strength(data.new_password)
    if pw_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=pw_error)
    current_user.password_hash = get_password_hash(data.new_password)
    current_user.password_changed_at = datetime.utcnow()
    db.commit()
    db.refresh(current_user)
    log_activity(db, "password_change", f"User changed password: {current_user.email}", user_id=current_user.id)
    return current_user


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ver_setting = db.query(SiteSetting).filter(SiteSetting.key == "about_content_version").first()
    current_version = int(ver_setting.value) if ver_setting else 1
    needs_approval = (
        current_user.about_approved_version is None
        or current_user.about_approved_version < current_version
    )
    mat_count = db.query(Material).filter(Material.owner_id == current_user.id).count()
    return {
        "email": current_user.email, "id": current_user.id, "is_admin": current_user.is_admin,
        "auth_provider": current_user.auth_provider or "local", "created_at": current_user.created_at,
        "max_upload_docs": current_user.max_upload_docs or 0,
        "default_visibility": current_user.default_visibility or "private",
        "about_approved_at": current_user.about_approved_at,
        "about_approved_version": current_user.about_approved_version,
        "needs_about_approval": needs_approval, "material_count": mat_count,
    }


@router.post("/approve-about")
def approve_about(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ver_setting = db.query(SiteSetting).filter(SiteSetting.key == "about_content_version").first()
    current_version = int(ver_setting.value) if ver_setting else 1
    current_user.about_approved_at = datetime.utcnow()
    current_user.about_approved_version = current_version
    db.commit()
    db.refresh(current_user)
    log_activity(db, "about_approved", f"User approved about v{current_version}", user_id=current_user.id)
    return {"approved_version": current_version, "approved_at": current_user.about_approved_at.isoformat()}


@router.get("/google-config")
def google_config():
    return {"client_id": settings.GOOGLE_CLIENT_ID or ""}


@router.post("/google", response_model=Token)
@limiter.limit("20/minute")
def google_login(request: Request, data: GoogleAuthRequest, db: Session = Depends(get_db)):
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests

    client_id = settings.GOOGLE_CLIENT_ID
    if not client_id:
        raise HTTPException(status_code=400, detail="Google SSO is not configured")

    try:
        idinfo = google_id_token.verify_oauth2_token(data.id_token, google_requests.Request(), client_id)
        email = idinfo.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="No email in Google token")
        if not idinfo.get("email_verified", False):
            raise HTTPException(status_code=400, detail="Email not verified by Google")
        if data.nonce:
            token_nonce = idinfo.get("nonce")
            if token_nonce != data.nonce:
                raise HTTPException(status_code=401, detail="Invalid credentials")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Google token validation failed: %s", e)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user:
        admin_emails = settings.get_admin_emails()
        is_admin = email.strip().lower() in admin_emails
        default_max = 0
        try:
            dmu_setting = db.query(SiteSetting).filter(SiteSetting.key == "default_max_upload_docs").first()
            if dmu_setting and dmu_setting.value:
                default_max = int(dmu_setting.value)
        except Exception:
            pass
        user = User(email=email.lower().strip(), password_hash="", auth_provider="google", is_admin=is_admin, max_upload_docs=default_max)
        db.add(user)
        db.commit()
        db.refresh(user)
        log_activity(db, "register", f"New user via Google SSO: {email}", user_id=user.id,
                     user_agent=_parse_ua(request.headers.get("user-agent", "")))
    else:
        if user.auth_provider == "local":
            user.auth_provider = "google"
            db.commit()
        log_activity(db, "login", f"Login via Google SSO: {email}", user_id=user.id,
                     user_agent=_parse_ua(request.headers.get("user-agent", "")))

    access_token = create_access_token(data={"sub": user.email}, expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/feedback")
async def submit_feedback(body: FeedbackCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Feedback message is required")
    fb = Feedback(user_id=current_user.id, page=body.page, message=body.message.strip(), action_log=body.action_log, status="new")
    db.add(fb)
    db.commit()
    db.refresh(fb)
    log_activity(db, "feedback", f"Feedback submitted on '{body.page}': {body.message[:80]}", user_id=current_user.id)
    return {"id": fb.id, "status": "submitted"}
