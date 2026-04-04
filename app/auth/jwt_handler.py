"""JWT生成与验证."""
from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import jwt

_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "readwise-dev-secret-change-in-production")
_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_DAYS = 7
_REFRESH_THRESHOLD_DAYS = 3  # refresh if less than 3 days remaining


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
