"""Password hashing, signed session cookies, login throttling, and the auth dependencies.

Sessions are HS256 JWTs stored in an HttpOnly cookie, so page JavaScript can never read them.
In production the browser reaches the API through the Netlify ``/api`` proxy, which makes the
cookie first-party. Each token carries the user's ``token_version``; bumping that number in the
database revokes every outstanding session for the user.
"""

from __future__ import annotations

import logging
import math
import os
import secrets
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from threading import Lock

import jwt
from fastapi import Depends, HTTPException, Response, status
from fastapi.security import APIKeyCookie
from pwdlib import PasswordHash
from pydantic import ValidationError
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .database import get_db

logger = logging.getLogger("studytrack")

SESSION_COOKIE = "studytrack_session"
JWT_ALGORITHM = "HS256"
MIN_SECRET_KEY_LENGTH = 32

_password_hash = PasswordHash.recommended()
# Verifying against this when an email is unknown keeps response times the same either way.
_DUMMY_HASH = _password_hash.hash(secrets.token_urlsafe(16))
_development_secret = secrets.token_urlsafe(48)

session_cookie_scheme = APIKeyCookie(
    name=SESSION_COOKIE,
    auto_error=False,
    description="Set by POST /auth/login. HttpOnly, so it is never readable by page JavaScript.",
)


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_production() -> bool:
    return os.getenv("ENVIRONMENT", "development").strip().lower() == "production"


def secret_key() -> str:
    key = os.getenv("SECRET_KEY", "")
    if key:
        return key
    if is_production():
        raise RuntimeError("SECRET_KEY must be set when ENVIRONMENT=production")
    # Development only: a per-process key means sessions end whenever the server restarts.
    return _development_secret


def session_hours() -> float:
    return float(os.getenv("SESSION_HOURS", "8"))


def cookie_secure() -> bool:
    return _env_flag("COOKIE_SECURE", default=is_production())


def check_settings() -> None:
    """Fail fast at startup instead of serving an insecure production deployment."""
    if not is_production():
        if not os.getenv("SECRET_KEY"):
            logger.warning("SECRET_KEY is not set; using a temporary key, so sessions end on restart")
        return
    if len(os.getenv("SECRET_KEY", "")) < MIN_SECRET_KEY_LENGTH:
        raise RuntimeError(f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters in production")
    if not cookie_secure():
        raise RuntimeError("COOKIE_SECURE must not be disabled in production")


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


def authenticate(db: Session, email: str, password: str) -> models.User | None:
    """Return the active user for these credentials, or None. Never says which part was wrong."""
    user = crud.get_user_by_email(db, email)
    if user is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return None
    valid, updated_hash = _password_hash.verify_and_update(password, user.password_hash)
    if not valid or not user.is_active:
        return None
    if updated_hash is not None:
        # The hashing parameters were upgraded since this hash was made; store the stronger one.
        crud.set_password_hash(db, user, updated_hash, revoke_sessions=False)
    return user


def create_session_token(user: models.User) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "ver": user.token_version,
        "iat": now,
        "exp": now + timedelta(hours=session_hours()),
    }
    return jwt.encode(payload, secret_key(), algorithm=JWT_ALGORITHM)


def set_session_cookie(response: Response, user: models.User) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user),
        max_age=int(session_hours() * 3600),
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=cookie_secure(), samesite="lax")


def _not_signed_in() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue")


def current_user(token: str | None = Depends(session_cookie_scheme), db: Session = Depends(get_db)) -> models.User:
    """Resolve the signed-in user from the session cookie, or answer 401."""
    if not token:
        raise _not_signed_in()
    try:
        payload = jwt.decode(
            token, secret_key(), algorithms=[JWT_ALGORITHM], options={"require": ["sub", "ver", "iat", "exp"]}
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError) as error:
        raise _not_signed_in() from error
    user = crud.get_user(db, user_id)
    if user is None or not user.is_active or user.token_version != payload["ver"]:
        raise _not_signed_in()
    return user


def require_admin(user: models.User = Depends(current_user)) -> models.User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access is required")
    return user


class LoginThrottle:
    """Lock an email out after repeated failed sign-ins.

    State lives in memory, which is enough for the single Render instance this app runs on.
    It is keyed by email rather than IP because forwarded client IPs can be spoofed.
    """

    def __init__(self, max_failures: int = 5, window_seconds: int = 15 * 60) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = {}
        self._lock = Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        attempts = self._failures.setdefault(key, deque())
        while attempts and now - attempts[0] >= self.window_seconds:
            attempts.popleft()
        return attempts

    def retry_after(self, key: str) -> int:
        """Seconds until ``key`` may try again, or 0 if it is not locked out."""
        now = time.monotonic()
        with self._lock:
            attempts = self._prune(key, now)
            if len(attempts) < self.max_failures:
                return 0
            return max(1, math.ceil(attempts[0] + self.window_seconds - now))

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune(key, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()


login_throttle = LoginThrottle()


def bootstrap_admin_from_env(db: Session) -> models.User | None:
    """Create the first administrator from env vars when the users table is empty.

    Render's free plan has no shell, so this is how a fresh deployment gets its first account.
    Once any user exists, the env vars are ignored and can be removed.
    """
    if crud.count_users(db) > 0:
        return None
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not email or not password:
        logger.warning(
            "No StudyTrack users exist. Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD, "
            "or run: python -m backend.manage create-user --role admin"
        )
        return None
    try:
        payload = schemas.UserCreate(
            email=email,
            full_name=os.getenv("BOOTSTRAP_ADMIN_NAME", "Administrator"),
            password=password,
            role="admin",
        )
    except ValidationError as error:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
        raise RuntimeError(f"BOOTSTRAP_ADMIN_* settings are invalid ({problems})") from error
    user = crud.create_user(db, payload, hash_password(payload.password))
    logger.info("Created bootstrap admin user id=%s", user.id)
    return user
