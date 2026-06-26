from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session, select

from app.auth import ADMIN_ONLY, AUTHED, get_current_user
from app.db import get_session
from app.models import (
    ChainOfTitleEntry,
    Rights,
    RightsEvidence,
    RightsOption,
    RightsStatusHistory,
    RightsWindow,
    User,
    Work,
)
from app.models.enums import RightScope
from app.schemas import (
    ChainOfTitleCreate,
    ChainOfTitleRead,
    RightsCreate,
    RightsDetail,
    RightsEvidenceCreate,
    RightsEvidenceRead,
    RightsOptionCreate,
    RightsOptionRead,
    RightsRead,
    RightsStatusHistoryCreate,
    RightsStatusHistoryRead,
    RightsUpdate,
    RightsWarningRead,
    RightsWindowCreate,
    RightsWindowRead,
)
from app.services import brain
from app.services import rights as rights_service
from app.utils import (
    Page,
    PageParams,
    apply_patch,
    ensure_exists,
    get_or_404,
    page_params,
    paginate,
)

router = APIRouter(prefix="/rights", tags=["rights"])

# Maps a right scope onto the matching profile column, so a status-history entry
# can also apply the change to the profile.
_SCOPE_FIELD = {
    RightScope.PRINT: "print_rights",
    RightScope.EBOOK: "ebook_rights",
    RightScope.AUDIOBOOK: "audiobook_rights",
    RightScope.FILM: "film_rights",
    RightScope.ADAPTATION: "adaptation_rights",
    RightScope.MERCHANDISING: "merchandising_rights",
}


@router.get("", response_model=Page[RightsRead])
def list_rights(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    work_id: Optional[str] = Query(default=None, description="Filter by work id"),
    territory: Optional[str] = Query(default=None),
    language: Optional[str] = Query(default=None),
) -> Page[RightsRead]:
    stmt = select(Rights)
    if work_id is not None:
        stmt = stmt.where(Rights.work_id == work_id)
    if territory is not None:
        stmt = stmt.where(Rights.territory == territory)
    if language is not None:
        stmt = stmt.where(Rights.language == language)
    stmt = stmt.order_by(Rights.created_at.desc())

    items, total = paginate(session, stmt, params)
    return Page[RightsRead](
        items=[RightsRead.model_validate(i) for i in items],
        total=total,
        skip=params.skip,
        limit=params.limit,
    )


# Declared before ``/{rights_id}`` so it is not shadowed by the catch-all.
@router.get("/warnings", response_model=list[RightsWarningRead])
def rights_warnings(
    session: Session = Depends(get_session),
    within_days: int = Query(default=90, ge=1, le=3650),
    work_id: Optional[str] = Query(default=None),
) -> list[RightsWarningRead]:
    warnings = rights_service.rights_warnings(
        session, within_days=within_days, work_id=work_id
    )
    return [RightsWarningRead(**w.__dict__) for w in warnings]


@router.get("/{rights_id}", response_model=RightsRead)
def get_rights(rights_id: str, session: Session = Depends(get_session)) -> Rights:
    return get_or_404(session, Rights, rights_id, name="Rights")


@router.get("/{rights_id}/detail", response_model=RightsDetail)
def get_rights_detail(
    rights_id: str, session: Session = Depends(get_session)
) -> RightsDetail:
    rights = get_or_404(session, Rights, rights_id, name="Rights")
    detail = RightsDetail.model_validate(rights)
    detail.windows = [RightsWindowRead.model_validate(w) for w in rights.windows]
    detail.options = [RightsOptionRead.model_validate(o) for o in rights.options]
    detail.chain_of_title = [
        ChainOfTitleRead.model_validate(c)
        for c in sorted(rights.chain_of_title, key=lambda e: e.position)
    ]
    detail.evidence = [RightsEvidenceRead.model_validate(e) for e in rights.evidence]
    detail.status_history = [
        RightsStatusHistoryRead.model_validate(h)
        for h in sorted(rights.status_history, key=lambda h: h.changed_at, reverse=True)
    ]
    return detail


@router.post(
    "", response_model=RightsRead, status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
)
def create_rights(
    payload: RightsCreate, session: Session = Depends(get_session)
) -> Rights:
    ensure_exists(session, Work, payload.work_id, name="Work")
    rights = Rights(**payload.model_dump())
    session.add(rights)
    work_id, story_world_id = brain.work_scope(session, rights.work_id)
    brain.emit(
        session, event_type=brain.BrainEventType.RIGHTS_UPDATED,
        aggregate_type="rights", aggregate_id=rights.id,
        work_id=work_id, story_world_id=story_world_id,
        changes={"created": True},
    )
    session.commit()
    session.refresh(rights)
    return rights


@router.patch("/{rights_id}", response_model=RightsRead, dependencies=AUTHED)
def update_rights(
    rights_id: str, payload: RightsUpdate, session: Session = Depends(get_session)
) -> Rights:
    rights = get_or_404(session, Rights, rights_id, name="Rights")
    apply_patch(rights, payload)
    session.add(rights)
    work_id, story_world_id = brain.work_scope(session, rights.work_id)
    brain.emit(
        session, event_type=brain.BrainEventType.RIGHTS_UPDATED,
        aggregate_type="rights", aggregate_id=rights.id,
        work_id=work_id, story_world_id=story_world_id,
        changes=payload.model_dump(exclude_unset=True),
    )
    session.commit()
    session.refresh(rights)
    return rights


@router.delete(
    "/{rights_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ADMIN_ONLY
)
def delete_rights(rights_id: str, session: Session = Depends(get_session)):
    rights = get_or_404(session, Rights, rights_id, name="Rights")
    work_id, story_world_id = brain.work_scope(session, rights.work_id)
    session.delete(rights)
    brain.emit(
        session, event_type=brain.BrainEventType.RIGHTS_UPDATED,
        aggregate_type="rights", aggregate_id=rights_id,
        work_id=work_id, story_world_id=story_world_id,
        changes={"deleted": True},
    )
    session.commit()


# --- term windows ----------------------------------------------------------


@router.get("/{rights_id}/windows", response_model=list[RightsWindowRead])
def list_windows(
    rights_id: str, session: Session = Depends(get_session)
) -> list[RightsWindowRead]:
    ensure_exists(session, Rights, rights_id, name="Rights")
    rows = session.exec(
        select(RightsWindow).where(RightsWindow.rights_id == rights_id)
    ).all()
    return [RightsWindowRead.model_validate(r) for r in rows]


@router.post(
    "/{rights_id}/windows", response_model=RightsWindowRead,
    status_code=status.HTTP_201_CREATED, dependencies=AUTHED,
)
def add_window(
    rights_id: str, payload: RightsWindowCreate, session: Session = Depends(get_session)
) -> RightsWindow:
    ensure_exists(session, Rights, rights_id, name="Rights")
    window = RightsWindow(rights_id=rights_id, **payload.model_dump())
    session.add(window)
    session.commit()
    session.refresh(window)
    return window


@router.delete(
    "/{rights_id}/windows/{window_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=AUTHED,
)
def delete_window(
    rights_id: str, window_id: str, session: Session = Depends(get_session)
):
    window = get_or_404(session, RightsWindow, window_id, name="RightsWindow")
    session.delete(window)
    session.commit()


# --- option periods --------------------------------------------------------


@router.get("/{rights_id}/options", response_model=list[RightsOptionRead])
def list_options(
    rights_id: str, session: Session = Depends(get_session)
) -> list[RightsOptionRead]:
    ensure_exists(session, Rights, rights_id, name="Rights")
    rows = session.exec(
        select(RightsOption).where(RightsOption.rights_id == rights_id)
    ).all()
    return [RightsOptionRead.model_validate(r) for r in rows]


@router.post(
    "/{rights_id}/options", response_model=RightsOptionRead,
    status_code=status.HTTP_201_CREATED, dependencies=AUTHED,
)
def add_option(
    rights_id: str, payload: RightsOptionCreate, session: Session = Depends(get_session)
) -> RightsOption:
    ensure_exists(session, Rights, rights_id, name="Rights")
    option = RightsOption(rights_id=rights_id, **payload.model_dump())
    session.add(option)
    session.commit()
    session.refresh(option)
    return option


@router.delete(
    "/{rights_id}/options/{option_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=AUTHED,
)
def delete_option(
    rights_id: str, option_id: str, session: Session = Depends(get_session)
):
    option = get_or_404(session, RightsOption, option_id, name="RightsOption")
    session.delete(option)
    session.commit()


# --- chain of title --------------------------------------------------------


@router.get("/{rights_id}/chain-of-title", response_model=list[ChainOfTitleRead])
def list_chain(
    rights_id: str, session: Session = Depends(get_session)
) -> list[ChainOfTitleRead]:
    ensure_exists(session, Rights, rights_id, name="Rights")
    rows = session.exec(
        select(ChainOfTitleEntry)
        .where(ChainOfTitleEntry.rights_id == rights_id)
        .order_by(ChainOfTitleEntry.position)
    ).all()
    return [ChainOfTitleRead.model_validate(r) for r in rows]


@router.post(
    "/{rights_id}/chain-of-title", response_model=ChainOfTitleRead,
    status_code=status.HTTP_201_CREATED, dependencies=AUTHED,
)
def add_chain_entry(
    rights_id: str, payload: ChainOfTitleCreate, session: Session = Depends(get_session)
) -> ChainOfTitleEntry:
    ensure_exists(session, Rights, rights_id, name="Rights")
    entry = ChainOfTitleEntry(rights_id=rights_id, **payload.model_dump())
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


@router.delete(
    "/{rights_id}/chain-of-title/{entry_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=AUTHED,
)
def delete_chain_entry(
    rights_id: str, entry_id: str, session: Session = Depends(get_session)
):
    entry = get_or_404(session, ChainOfTitleEntry, entry_id, name="ChainOfTitleEntry")
    session.delete(entry)
    session.commit()


# --- evidence --------------------------------------------------------------


@router.get("/{rights_id}/evidence", response_model=list[RightsEvidenceRead])
def list_evidence(
    rights_id: str, session: Session = Depends(get_session)
) -> list[RightsEvidenceRead]:
    ensure_exists(session, Rights, rights_id, name="Rights")
    rows = session.exec(
        select(RightsEvidence).where(RightsEvidence.rights_id == rights_id)
    ).all()
    return [RightsEvidenceRead.model_validate(r) for r in rows]


@router.post(
    "/{rights_id}/evidence", response_model=RightsEvidenceRead,
    status_code=status.HTTP_201_CREATED, dependencies=AUTHED,
)
def add_evidence(
    rights_id: str, payload: RightsEvidenceCreate, session: Session = Depends(get_session)
) -> RightsEvidence:
    ensure_exists(session, Rights, rights_id, name="Rights")
    evidence = RightsEvidence(rights_id=rights_id, **payload.model_dump())
    session.add(evidence)
    session.commit()
    session.refresh(evidence)
    return evidence


@router.delete(
    "/{rights_id}/evidence/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=AUTHED,
)
def delete_evidence(
    rights_id: str, evidence_id: str, session: Session = Depends(get_session)
):
    evidence = get_or_404(session, RightsEvidence, evidence_id, name="RightsEvidence")
    session.delete(evidence)
    session.commit()


# --- status history --------------------------------------------------------


@router.get("/{rights_id}/status-history", response_model=list[RightsStatusHistoryRead])
def list_status_history(
    rights_id: str, session: Session = Depends(get_session)
) -> list[RightsStatusHistoryRead]:
    ensure_exists(session, Rights, rights_id, name="Rights")
    rows = session.exec(
        select(RightsStatusHistory)
        .where(RightsStatusHistory.rights_id == rights_id)
        .order_by(RightsStatusHistory.changed_at.desc())
    ).all()
    return [RightsStatusHistoryRead.model_validate(r) for r in rows]


@router.post(
    "/{rights_id}/status-history", response_model=RightsStatusHistoryRead,
    status_code=status.HTTP_201_CREATED, dependencies=AUTHED,
)
def record_status_change(
    rights_id: str,
    payload: RightsStatusHistoryCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RightsStatusHistory:
    rights = get_or_404(session, Rights, rights_id, name="Rights")
    entry = RightsStatusHistory(
        rights_id=rights_id,
        scope=payload.scope,
        from_status=payload.from_status,
        to_status=payload.to_status,
        note=payload.note,
        changed_by_id=user.id,
    )
    # Apply the change to the matching profile column when the scope maps to one.
    field = _SCOPE_FIELD.get(payload.scope)
    if field is not None:
        setattr(rights, field, payload.to_status)
        session.add(rights)
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry
