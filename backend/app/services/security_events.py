"""Security-event recording + suspicious-burst detection (Prompt 15).

An append-only log of security-relevant events (failed mapping, revoked-token
use, disabled member, project-denied tool call) and benign audit lifecycle
(token/identity changes). When a single principal accrues several failures inside
a short window, an additional CRITICAL ``repeated_failures`` event is raised.

Recording happens on the caller's session. Failure paths pass ``commit=True`` so
the event persists even when the surrounding request is about to 401 or its tool
call is about to roll back.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlmodel import Session, func, select

from app.config import settings
from app.models import SecurityEvent
from app.models.base import utcnow
from app.models.enums import SecurityEventSeverity, SecurityEventType

# Default severity per event type (callers may override).
_DEFAULT_SEVERITY: dict[SecurityEventType, SecurityEventSeverity] = {
    SecurityEventType.SERVICE_AUTH_FAILED: SecurityEventSeverity.WARNING,
    SecurityEventType.INVALID_SIGNATURE: SecurityEventSeverity.WARNING,
    SecurityEventType.MAPPING_FAILED: SecurityEventSeverity.WARNING,
    SecurityEventType.UNLINKED_USER: SecurityEventSeverity.WARNING,
    SecurityEventType.DISABLED_MEMBER: SecurityEventSeverity.WARNING,
    SecurityEventType.PROJECT_DENIED: SecurityEventSeverity.WARNING,
    SecurityEventType.REVOKED_TOKEN_USE: SecurityEventSeverity.WARNING,
    SecurityEventType.EXPIRED_TOKEN_USE: SecurityEventSeverity.WARNING,
    SecurityEventType.REPEATED_FAILURES: SecurityEventSeverity.CRITICAL,
    SecurityEventType.TOKEN_CREATED: SecurityEventSeverity.INFO,
    SecurityEventType.TOKEN_ROTATED: SecurityEventSeverity.INFO,
    SecurityEventType.TOKEN_REVOKED: SecurityEventSeverity.INFO,
    SecurityEventType.IDENTITY_LINKED: SecurityEventSeverity.INFO,
    SecurityEventType.IDENTITY_VERIFIED: SecurityEventSeverity.INFO,
    SecurityEventType.IDENTITY_DISABLED: SecurityEventSeverity.INFO,
}

_FAILURE_SEVERITIES = (SecurityEventSeverity.WARNING, SecurityEventSeverity.CRITICAL)


def record_security_event(
    session: Session,
    *,
    event_type: SecurityEventType,
    severity: Optional[SecurityEventSeverity] = None,
    source: str = "",
    supervoid_user_id: Optional[str] = None,
    librechat_user_id: Optional[str] = None,
    email: Optional[str] = None,
    reason: Optional[str] = None,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
    token_id: Optional[str] = None,
    request_id: Optional[str] = None,
    detail: Optional[dict] = None,
    commit: bool = False,
) -> SecurityEvent:
    """Append a security event (and, for failures, maybe a repeated-failures
    alert). ``commit=True`` for paths whose transaction is about to unwind."""
    severity = severity or _DEFAULT_SEVERITY.get(event_type, SecurityEventSeverity.WARNING)
    event = SecurityEvent(
        event_type=event_type, severity=severity, source=source,
        supervoid_user_id=supervoid_user_id, librechat_user_id=librechat_user_id,
        email=(email or None), reason=reason, work_id=work_id,
        story_world_id=story_world_id, token_id=token_id, request_id=request_id,
        detail=detail or {},
    )
    session.add(event)
    session.flush()

    if severity in _FAILURE_SEVERITIES and event_type != SecurityEventType.REPEATED_FAILURES:
        _maybe_flag_repeated(session, event, source=source)

    if commit:
        session.commit()
    return event


def _maybe_flag_repeated(session: Session, event: SecurityEvent, *, source: str) -> None:
    """Raise a CRITICAL repeated-failures alert when a principal crosses the
    failure threshold inside the window (deduped per window)."""
    principal_email = event.email
    principal_user = event.supervoid_user_id
    if not principal_email and not principal_user:
        return
    window_start = utcnow() - timedelta(
        seconds=settings.security_repeated_failure_window_seconds
    )

    def _principal_filter(stmt):
        if principal_email:
            return stmt.where(SecurityEvent.email == principal_email)
        return stmt.where(SecurityEvent.supervoid_user_id == principal_user)

    count = int(session.exec(_principal_filter(
        select(func.count(SecurityEvent.id)).where(
            SecurityEvent.created_at >= window_start,
            SecurityEvent.severity.in_(_FAILURE_SEVERITIES),
            SecurityEvent.event_type != SecurityEventType.REPEATED_FAILURES,
        )
    )).one() or 0)
    if count < settings.security_repeated_failure_threshold:
        return
    # Dedupe: only one repeated-failures alert per principal per window.
    existing = session.exec(_principal_filter(
        select(SecurityEvent.id).where(
            SecurityEvent.created_at >= window_start,
            SecurityEvent.event_type == SecurityEventType.REPEATED_FAILURES,
        )
    )).first()
    if existing is not None:
        return
    session.add(SecurityEvent(
        event_type=SecurityEventType.REPEATED_FAILURES,
        severity=SecurityEventSeverity.CRITICAL, source=source,
        supervoid_user_id=principal_user, librechat_user_id=event.librechat_user_id,
        email=principal_email,
        reason=f"{count} security failures within "
               f"{settings.security_repeated_failure_window_seconds}s",
        detail={"window_count": count},
    ))
    session.flush()


def list_security_events(
    session: Session,
    *,
    event_type: Optional[SecurityEventType] = None,
    severity: Optional[SecurityEventSeverity] = None,
    source: Optional[str] = None,
    email: Optional[str] = None,
    supervoid_user_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[SecurityEvent]:
    stmt = select(SecurityEvent)
    if event_type is not None:
        stmt = stmt.where(SecurityEvent.event_type == event_type)
    if severity is not None:
        stmt = stmt.where(SecurityEvent.severity == severity)
    if source:
        stmt = stmt.where(SecurityEvent.source == source)
    if email:
        stmt = stmt.where(SecurityEvent.email == email)
    if supervoid_user_id:
        stmt = stmt.where(SecurityEvent.supervoid_user_id == supervoid_user_id)
    stmt = stmt.order_by(SecurityEvent.created_at.desc()).offset(offset).limit(limit)
    return list(session.exec(stmt).all())
