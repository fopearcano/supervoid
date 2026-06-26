"""Versioned-record helpers for the Brain's stable instruction layer.

Each family (Studio Constitution, assistant profiles, context templates, the
safety/approval policy, the terminology glossary) is a parent + append-only
version child. The parent's ``current_version`` selects the live version; adding
a version bumps the pointer in the same transaction. Records are never edited in
place — a change is always a new immutable version, so the prompt-prefix cache
can invalidate deterministically on a version change.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from app.models import (
    AssistantProfile,
    AssistantProfileVersion,
    ContextTemplate,
    ContextTemplateVersion,
    SafetyApprovalPolicy,
    SafetyApprovalPolicyVersion,
    StudioConstitution,
    StudioConstitutionVersion,
    TerminologyGlossary,
    TerminologyGlossaryVersion,
)

# (parent, version, fk attribute) wiring for the generic helpers.
_FAMILIES = {
    "constitution": (StudioConstitution, StudioConstitutionVersion, "constitution_id"),
    "profile": (AssistantProfile, AssistantProfileVersion, "profile_id"),
    "template": (ContextTemplate, ContextTemplateVersion, "template_id"),
    "policy": (SafetyApprovalPolicy, SafetyApprovalPolicyVersion, "policy_id"),
    "glossary": (TerminologyGlossary, TerminologyGlossaryVersion, "glossary_id"),
}


def _get_parent(session: Session, parent_cls, key: str):
    return session.exec(select(parent_cls).where(parent_cls.key == key)).first()


def get_active(session: Session, family: str, key: str):
    """Return ``(parent, active_version)`` for ``key`` — the version row whose
    ``version == parent.current_version``. ``(None, None)`` if absent."""
    parent_cls, version_cls, fk = _FAMILIES[family]
    parent = _get_parent(session, parent_cls, key)
    if parent is None:
        return None, None
    version = session.exec(
        select(version_cls).where(
            getattr(version_cls, fk) == parent.id,
            version_cls.version == parent.current_version,
        )
    ).first()
    return parent, version


def add_version(
    session: Session,
    family: str,
    key: str,
    *,
    fields: dict,
    created_by_id: Optional[str] = None,
) -> object:
    """Append a new version to ``key`` and bump the parent's pointer, atomically.

    The parent must already exist (seeded). Returns the new version row.
    """
    parent_cls, version_cls, fk = _FAMILIES[family]
    parent = _get_parent(session, parent_cls, key)
    if parent is None:
        raise ValueError(f"{family} '{key}' does not exist")
    new_version = parent.current_version + 1
    version = version_cls(
        version=new_version,
        created_by_id=created_by_id,
        **{fk: parent.id},
        **fields,
    )
    parent.current_version = new_version
    session.add(version)
    session.add(parent)
    session.flush()
    return version


def list_versions(session: Session, family: str, key: str, *, limit: int = 50) -> list:
    parent_cls, version_cls, fk = _FAMILIES[family]
    parent = _get_parent(session, parent_cls, key)
    if parent is None:
        return []
    return list(
        session.exec(
            select(version_cls)
            .where(getattr(version_cls, fk) == parent.id)
            .order_by(version_cls.version.desc())
            .limit(limit)
        ).all()
    )


def list_profiles(session: Session) -> list:
    """All enabled assistant profiles with their active version, ordered by key."""
    parents = session.exec(
        select(AssistantProfile)
        .where(AssistantProfile.enabled == True)  # noqa: E712
        .order_by(AssistantProfile.key)
    ).all()
    out = []
    for p in parents:
        _, v = get_active(session, "profile", p.key)
        out.append((p, v))
    return out
