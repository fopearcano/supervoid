"""Private curation service for the public reader.

Owns the controlled hand-off from private records to the public projection and
the gated publication lifecycle (validate → request approval → approve →
publish), preserving history as ``PublicationEvent`` rows.

Invariants:
- the public reader is never written automatically; every step is an explicit,
  authenticated curator action;
- a private file is never used — hand-off requires an explicitly selected public
  derivative (a ``PublicMediaAsset``);
- credits, licences and provenance are validated before publication;
- unpublishing flips visibility only — the private source is never deleted;
- publication history is append-only.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import (
    AssetVersion,
    CurationStatus,
    GraphicNovelPage,
    LicenceRecord,
    LicenceReviewState,
    ProvenanceRecord,
    PublicationAction,
    PublicationApproval,
    PublicationApprovalStatus,
    PublicationEvent,
    PublicMediaAsset,
    PublishedChapter,
    PublishedPage,
    PublishedPanel,
    PublishedStatus,
    PublishedVolume,
    PublishedWork,
    User,
)
from app.models.base import utcnow


# --- history ---------------------------------------------------------------


def record_event(
    session: Session,
    work: PublishedWork,
    action: PublicationAction,
    *,
    user: Optional[User] = None,
    from_status: Optional[PublishedStatus] = None,
    to_status: Optional[PublishedStatus] = None,
    note: Optional[str] = None,
    detail: Optional[dict] = None,
) -> PublicationEvent:
    event = PublicationEvent(
        published_work_id=work.id,
        action=action,
        actor_id=user.id if user else None,
        from_status=from_status,
        to_status=to_status,
        note=note,
        detail=detail or {},
    )
    session.add(event)
    return event


def _work_for_chapter(
    session: Session, chapter: PublishedChapter
) -> Optional[PublishedWork]:
    volume = session.get(PublishedVolume, chapter.published_volume_id)
    if volume is None:
        return None
    return session.get(PublishedWork, volume.published_work_id)


# --- validation ------------------------------------------------------------


def validate_for_publication(session: Session, work: PublishedWork) -> dict:
    """Validate credits, structure, licences and provenance before publication."""
    issues: list[dict] = []

    def add(code: str, severity: str, message: str, target_id: Optional[str] = None):
        issues.append(
            {"code": code, "severity": severity, "message": message, "target_id": target_id}
        )

    if not (work.author_credit or "").strip():
        add("missing_author_credit", "error", "An author credit is required to publish.")
    if not (work.artist_credit or "").strip():
        add("missing_artist_credit", "warning", "No artist credit set.")
    if not (work.cover_image or "").strip():
        add("missing_cover", "warning", "No cover image set.")

    volumes = work.volumes
    if not volumes:
        add("no_volumes", "error", "Publication needs at least one volume.")

    page_count = 0
    for volume in volumes:
        for chapter in volume.chapters:
            for page in chapter.pages:
                page_count += 1
                if not (page.image_path or "").strip():
                    add("page_no_image", "error",
                        f"Page {page.page_number} has no public image.", page.id)
                if page.source_asset_version_id:
                    _validate_asset_backed_page(session, page, add)
    if page_count == 0:
        add("no_pages", "error", "Publication needs at least one page.")

    errors = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")
    return {"ok": errors == 0, "errors": errors, "warnings": warnings, "issues": issues}


def _validate_asset_backed_page(session: Session, page: PublishedPage, add) -> None:
    version = session.get(AssetVersion, page.source_asset_version_id)
    if version is None:
        add("missing_source_version", "warning",
            f"Page {page.page_number}: source asset version not found.", page.id)
        return
    provenance = session.exec(
        select(ProvenanceRecord).where(
            ProvenanceRecord.asset_version_id == version.id
        )
    ).first()
    if provenance is None:
        add("missing_provenance", "error",
            f"Page {page.page_number}: source has no provenance record.", page.id)

    licences = session.exec(
        select(LicenceRecord).where(LicenceRecord.asset_id == version.asset_id)
    ).all()
    today = date.today()
    cleared = any(
        lic.review_state == LicenceReviewState.APPROVED
        and (lic.expiration_date is None or lic.expiration_date >= today)
        for lic in licences
    )
    if not licences:
        add("missing_licence", "error",
            f"Page {page.page_number}: source asset has no licence record.", page.id)
    elif not cleared:
        add("licence_not_cleared", "error",
            f"Page {page.page_number}: source licence is not approved/current.", page.id)


# --- approval & publication lifecycle --------------------------------------


def latest_approval(
    session: Session, work_id: str
) -> Optional[PublicationApproval]:
    return session.exec(
        select(PublicationApproval)
        .where(PublicationApproval.published_work_id == work_id)
        .order_by(PublicationApproval.created_at.desc())
    ).first()


def request_approval(
    session: Session, work: PublishedWork, *, user: User
) -> PublicationApproval:
    validation = validate_for_publication(session, work)
    approval = PublicationApproval(
        published_work_id=work.id,
        status=PublicationApprovalStatus.PENDING,
        requested_by_id=user.id,
        validation=validation,
    )
    session.add(approval)
    record_event(
        session, work, PublicationAction.APPROVAL_REQUESTED,
        user=user, detail={"validation_ok": validation["ok"]},
    )
    return approval


def decide_approval(
    session: Session,
    approval: PublicationApproval,
    *,
    approve: bool,
    user: User,
    note: Optional[str] = None,
) -> PublicationApproval:
    if approval.status != PublicationApprovalStatus.PENDING:
        raise HTTPException(
            status_code=400, detail=f"Approval is already {approval.status.value}."
        )
    work = session.get(PublishedWork, approval.published_work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="Published work not found.")

    if approve:
        validation = validate_for_publication(session, work)
        if not validation["ok"]:
            raise HTTPException(
                status_code=400,
                detail="Cannot approve: validation has blocking errors.",
            )
        approval.validation = validation
        approval.status = PublicationApprovalStatus.APPROVED
    else:
        approval.status = PublicationApprovalStatus.REJECTED

    approval.decided_by_id = user.id
    approval.decided_at = utcnow()
    approval.note = note
    session.add(approval)
    record_event(
        session, work,
        PublicationAction.APPROVED if approve else PublicationAction.REJECTED,
        user=user, note=note,
    )
    return approval


def publish(session: Session, work: PublishedWork, *, user: User) -> PublishedWork:
    approval = latest_approval(session, work.id)
    if approval is None or approval.status != PublicationApprovalStatus.APPROVED:
        raise HTTPException(
            status_code=409,
            detail="Publication requires an approved request.",
        )
    validation = validate_for_publication(session, work)
    if not validation["ok"]:
        raise HTTPException(
            status_code=400, detail="Cannot publish: validation has blocking errors."
        )
    previous = work.status
    work.status = PublishedStatus.PUBLISHED
    if work.publication_date is None:
        work.publication_date = date.today()
    session.add(work)
    record_event(
        session, work, PublicationAction.PUBLISHED,
        user=user, from_status=previous, to_status=PublishedStatus.PUBLISHED,
    )
    return work


def unpublish(
    session: Session, work: PublishedWork, *, user: User, note: Optional[str] = None
) -> PublishedWork:
    """Make a work non-public again. Flips visibility only — the public
    projection rows and the private source are all preserved."""
    previous = work.status
    work.status = PublishedStatus.DRAFT
    session.add(work)
    record_event(
        session, work, PublicationAction.UNPUBLISHED,
        user=user, from_status=previous, to_status=PublishedStatus.DRAFT, note=note,
    )
    return work


def set_visibility(
    session: Session,
    work: PublishedWork,
    status: PublishedStatus,
    *,
    user: User,
    note: Optional[str] = None,
) -> PublishedWork:
    if status == PublishedStatus.PUBLISHED:
        raise HTTPException(
            status_code=400,
            detail="Use the publish endpoint to publish (approval-gated).",
        )
    previous = work.status
    work.status = status
    session.add(work)
    action = (
        PublicationAction.ARCHIVED
        if status == PublishedStatus.ARCHIVED
        else PublicationAction.UPDATED
    )
    record_event(
        session, work, action, user=user,
        from_status=previous, to_status=status, note=note,
    )
    return work


def schedule(
    session: Session,
    work: PublishedWork,
    publication_date: date,
    *,
    user: User,
    note: Optional[str] = None,
) -> PublishedWork:
    work.publication_date = publication_date
    session.add(work)
    record_event(
        session, work, PublicationAction.SCHEDULED, user=user, note=note,
        detail={"publication_date": publication_date.isoformat()},
    )
    return work


# --- controlled hand-off ---------------------------------------------------


def hand_off_page(session: Session, req, *, user: User) -> PublishedPage:
    """Hand a private GraphicNovelPage off to the public projection using an
    explicitly selected public derivative. Never references a private file."""
    gn_page = session.get(GraphicNovelPage, req.gn_page_id)
    if gn_page is None:
        raise HTTPException(status_code=404, detail="GraphicNovelPage not found.")
    media = session.get(PublicMediaAsset, req.public_media_asset_id)
    if media is None:
        raise HTTPException(
            status_code=404,
            detail="Public derivative (PublicMediaAsset) not found — selection is required.",
        )
    chapter = session.get(PublishedChapter, req.chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Published chapter not found.")

    page_number = req.page_number if req.page_number is not None else gn_page.page_number

    # Reuse the public page if this private page was already handed off.
    page = (
        session.get(PublishedPage, gn_page.published_page_id)
        if gn_page.published_page_id
        else None
    )
    if page is None:
        page = PublishedPage(
            published_chapter_id=chapter.id,
            page_number=page_number,
            image_path=media.file_path,  # PUBLIC derivative path, never private
        )
        session.add(page)
        session.flush()
    else:
        page.published_chapter_id = chapter.id
        page.page_number = page_number
        page.image_path = media.file_path

    page.alt_text = req.alt_text or page.alt_text or gn_page.dialogue_summary
    page.source_gn_page_id = gn_page.id
    page.source_asset_version_id = req.source_asset_version_id
    session.add(page)
    session.flush()

    if req.import_panels:
        # Idempotent: replace any previously imported panels.
        for existing in list(page.panels):
            session.delete(existing)
        session.flush()
        for panel in sorted(
            gn_page.panels, key=lambda p: (p.position, p.panel_number)
        ):
            session.add(
                PublishedPanel(
                    published_page_id=page.id,
                    panel_number=panel.panel_number,
                    reading_order=panel.position,
                    x=panel.x, y=panel.y, width=panel.width, height=panel.height,
                    caption=panel.dialogue or panel.captions,
                    source_panel_id=panel.id,
                )
            )

    gn_page.published_page_id = page.id
    gn_page.curation_status = CurationStatus.HANDED_OFF
    session.add(gn_page)

    work = _work_for_chapter(session, chapter)
    if work is not None:
        record_event(
            session, work, PublicationAction.PAGE_HANDED_OFF, user=user,
            detail={"page_id": page.id, "gn_page_id": gn_page.id, "media_id": media.id},
        )
    return page
