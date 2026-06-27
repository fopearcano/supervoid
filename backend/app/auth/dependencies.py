"""FastAPI dependencies for authentication and role-based access control."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select

from app.auth.security import decode_token
from app.config import settings
from app.db import get_session
from app.models import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_prefix}/auth/login",
    auto_error=True,
)


_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    try:
        payload = decode_token(token)
        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise _CREDENTIALS_EXCEPTION
    except jwt.PyJWTError as exc:
        raise _CREDENTIALS_EXCEPTION from exc

    user = session.get(User, subject)
    if user is None or not user.is_active:
        raise _CREDENTIALS_EXCEPTION
    return user


def require_role(*allowed: UserRole):
    """Dependency factory that allows only callers whose role is in `allowed`."""
    allowed_set: frozenset[UserRole] = frozenset(allowed)

    def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
        return user

    return _dependency


def require_any_role(allowed: Iterable[UserRole]):
    """Variant accepting an iterable of roles. Useful for shared role tuples."""
    return require_role(*allowed)


# Reusable dependency lists for FastAPI route decorators. Define once, attach
# everywhere — avoids 21 copies of the same Depends() call across CRUD routers.
AUTHED: list = [Depends(get_current_user)]
ADMIN_ONLY: list = [Depends(require_role(UserRole.ADMIN))]


# --- Brain Gateway: opaque bearer-token authentication ---------------------
@dataclass
class BrainPrincipal:
    """The authenticated principal behind a Brain access token."""

    user: User
    token: "BrainAccessToken"  # noqa: F821


def get_brain_principal(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> BrainPrincipal:
    """Authenticate a Brain Gateway request with a dedicated access token (NOT
    the browser JWT). Looks the token up by its SHA-256 hash, rejects revoked /
    expired tokens and inactive owners, and stamps ``last_used_at``."""
    from datetime import timezone

    from app.auth.security import hash_brain_token
    from app.models import BrainAccessToken
    from app.models.base import utcnow
    from app.models.enums import SecurityEventType
    from app.services import security_events as sec

    row = session.exec(
        select(BrainAccessToken).where(
            BrainAccessToken.token_hash == hash_brain_token(token)
        )
    ).first()
    if row is None:
        raise _CREDENTIALS_EXCEPTION
    now = utcnow()
    # DB datetimes round-trip naive on SQLite; treat them as UTC for comparison.
    expires = row.expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if row.revoked_at is not None:
        sec.record_security_event(
            session, event_type=SecurityEventType.REVOKED_TOKEN_USE, source="gateway",
            supervoid_user_id=row.user_id, token_id=row.id,
            reason="revoked token presented", commit=True,
        )
        raise _CREDENTIALS_EXCEPTION
    if expires is not None and expires < now:
        sec.record_security_event(
            session, event_type=SecurityEventType.EXPIRED_TOKEN_USE, source="gateway",
            supervoid_user_id=row.user_id, token_id=row.id,
            reason="expired token presented", commit=True,
        )
        raise _CREDENTIALS_EXCEPTION
    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        if user is not None and not user.is_active:
            sec.record_security_event(
                session, event_type=SecurityEventType.DISABLED_MEMBER, source="gateway",
                supervoid_user_id=user.id, email=user.email, token_id=row.id,
                reason="disabled member presented a gateway token", commit=True,
            )
        raise _CREDENTIALS_EXCEPTION
    # get_session() does not auto-commit, so persist last_used explicitly.
    row.last_used_at = now
    session.add(row)
    session.commit()
    return BrainPrincipal(user=user, token=row)


BRAIN_AUTHED: list = [Depends(get_brain_principal)]
