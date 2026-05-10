"""JWT生成与验证."""
from __future__ import annotations
import logging
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import jwt
from app.config import is_production_env

load_dotenv()
logger = logging.getLogger(__name__)

_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
_DEFAULT_SECRET = "readwise-dev-secret-change-in-production-2026"
_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_DAYS = 7
_REFRESH_THRESHOLD_DAYS = 3  # refresh if less than 3 days remaining

if not _SECRET_KEY:
    if is_production_env():
        raise RuntimeError("JWT_SECRET_KEY must be set in production")
    logger.warning(
        "JWT_SECRET_KEY is not set. Using the default dev secret – "
        "set JWT_SECRET_KEY in production to a strong random value."
    )
    _SECRET_KEY = _DEFAULT_SECRET
elif len(_SECRET_KEY.encode("utf-8")) < 32:
    if is_production_env():
        raise RuntimeError("JWT_SECRET_KEY must be at least 32 bytes in production")
    logger.warning(
        "JWT_SECRET_KEY is shorter than 32 bytes. Using the default dev secret – "
        "set JWT_SECRET_KEY to a strong random value."
    )
    _SECRET_KEY = _DEFAULT_SECRET


def create_access_token(user_id: str, role: str = "user") -> str:
    """Generate a JWT access token for the given user."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=_ACCESS_TOKEN_EXPIRE_DAYS)
    payload: Dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and verify a JWT token. Raises jwt.PyJWTError on failure."""
    return jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])


def should_refresh(token: str) -> bool:
    """Return True if the token has less than _REFRESH_THRESHOLD_DAYS remaining."""
    try:
        payload = decode_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        remaining = exp - datetime.now(timezone.utc)
        return remaining < timedelta(days=_REFRESH_THRESHOLD_DAYS)
    except Exception:
        return False
