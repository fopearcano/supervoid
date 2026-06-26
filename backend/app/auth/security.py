"""Stateless security primitives: password hashing and JWT encode/decode."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# --- Brain access tokens (opaque bearer secrets for the Brain Gateway) ------
# Unlike a user password, a Brain token must be looked up by its hash, so the
# hash has to be deterministic — a plain SHA-256 of a high-entropy secret (NOT
# bcrypt, which is salted/non-deterministic). The plaintext is shown to the
# owner exactly once at creation/rotation and never stored.
def generate_brain_token() -> str:
    """A high-entropy, URL-safe Brain access secret (~43 chars)."""
    return "sk-brain-" + secrets.token_urlsafe(32)


def hash_brain_token(plain: str) -> str:
    """Deterministic SHA-256 hex digest used to look a token up by value."""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    *,
    subject: str,
    role: str,
    expires_minutes: int | None = None,
) -> tuple[str, datetime]:
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "role": role, "exp": expires}
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expires


def decode_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
    )
