"""Password hashing (bcrypt) and JWT encode/decode — fail-closed.

Uses bcrypt directly (hashpw/checkpw), NOT passlib (unmaintained, breaks with
bcrypt>=4.1). JWT is pinned to HS256 and always requires `exp`.
"""
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import settings


def hash_password(password: str) -> str:
    """bcrypt hash (truncate input at 72 bytes — bcrypt's hard limit)."""
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> int:
    """Decode + validate a JWT. Returns user_id (int) or raises jwt.PyJWTError."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    return int(payload["sub"])
