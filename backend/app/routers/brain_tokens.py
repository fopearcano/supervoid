"""Brain access token management (private UI, JWT-authenticated).

Users create / rotate / revoke their own Brain Gateway tokens here, logged in
with the ordinary browser session. The plaintext secret is returned exactly once
(on create and rotate) and is never recoverable — only its SHA-256 hash is
stored.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.auth import generate_brain_token, get_current_user, hash_brain_token
from app.db import get_session
from app.models import BrainAccessToken, User
from app.models.base import utcnow
from app.models.enums import SecurityEventType
from app.schemas.brain_token import (
    BrainTokenCreate,
    BrainTokenMeta,
    BrainTokenSecret,
)
from app.services import security_events as sec


def _token_audit(session: Session, user: User, token: BrainAccessToken, event_type) -> None:
    """Append a benign audit-trail event for a token lifecycle change."""
    sec.record_security_event(
        session, event_type=event_type, source="api",
        supervoid_user_id=user.id, email=user.email, token_id=token.id,
        reason=token.name,
    )

router = APIRouter(prefix="/brain-tokens", tags=["brain-tokens"])


def _meta(token: BrainAccessToken) -> BrainTokenMeta:
    return BrainTokenMeta(
        id=token.id, name=token.name, token_prefix=token.token_prefix,
        created_at=token.created_at, last_used_at=token.last_used_at,
        expires_at=token.expires_at, revoked_at=token.revoked_at,
        project_restrictions=token.project_restrictions,
    )


def _owned(session: Session, token_id: str, user: User) -> BrainAccessToken:
    token = session.get(BrainAccessToken, token_id)
    if token is None or token.user_id != user.id:
        raise HTTPException(status_code=404, detail="Token not found")
    return token


@router.get("", response_model=list[BrainTokenMeta])
def list_tokens(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[BrainTokenMeta]:
    rows = session.exec(
        select(BrainAccessToken)
        .where(BrainAccessToken.user_id == user.id)
        .order_by(BrainAccessToken.created_at.desc())
    ).all()
    return [_meta(t) for t in rows]


@router.post("", response_model=BrainTokenSecret, status_code=status.HTTP_201_CREATED)
def create_token(
    body: BrainTokenCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BrainTokenSecret:
    secret = generate_brain_token()
    expires_at = (
        utcnow() + timedelta(days=body.expires_in_days) if body.expires_in_days else None
    )
    token = BrainAccessToken(
        user_id=user.id,
        name=body.name,
        token_hash=hash_brain_token(secret),
        token_prefix=secret[:12],
        expires_at=expires_at,
        project_restrictions=[r.model_dump() for r in body.project_restrictions],
    )
    session.add(token)
    session.flush()
    _token_audit(session, user, token, SecurityEventType.TOKEN_CREATED)
    session.commit()
    session.refresh(token)
    return BrainTokenSecret(token=_meta(token), secret=secret)


@router.post("/{token_id}/rotate", response_model=BrainTokenSecret)
def rotate_token(
    token_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BrainTokenSecret:
    """Issue a fresh secret for an existing token (the old secret stops working
    immediately). Revoked tokens cannot be rotated."""
    token = _owned(session, token_id, user)
    if token.revoked_at is not None:
        raise HTTPException(status_code=400, detail="Cannot rotate a revoked token")
    secret = generate_brain_token()
    token.token_hash = hash_brain_token(secret)
    token.token_prefix = secret[:12]
    token.last_used_at = None
    session.add(token)
    _token_audit(session, user, token, SecurityEventType.TOKEN_ROTATED)
    session.commit()
    session.refresh(token)
    return BrainTokenSecret(token=_meta(token), secret=secret)


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(
    token_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Revoke a token. Revocation takes effect immediately — the gateway rejects
    a revoked token on its next request."""
    token = _owned(session, token_id, user)
    if token.revoked_at is None:
        token.revoked_at = utcnow()
        session.add(token)
        _token_audit(session, user, token, SecurityEventType.TOKEN_REVOKED)
        session.commit()
