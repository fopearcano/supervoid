"""Private curation CMS for the public Graphic Novel Webviewer.

Mounted under the authenticated ``/api`` prefix — this is the *private* admin
surface. It writes the public projection models and drives the gated publication
lifecycle and the controlled hand-off from private records. It does NOT weaken
public/private separation: the public ``/public`` router stays read-only and
only ever serves PUBLISHED / UNLISTED works.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.auth import ADMIN_ONLY, AUTHED, get_current_user
from app.db import get_session
from app.models import (
    PublicationApproval,
    PublicationEvent,
    PublicHotspot,
    PublicMediaAsset,
    PublishedChapter,
    PublishedPage,
    PublishedPanel,
    PublishedStatus,
    PublishedVolume,
    PublishedWork,
    User,
)
from app.schemas.curation import (
    ApprovalDecisionRequest,
    CreateFromWorkRequest,
    PageHandoffRequest,
    PublicationApprovalRead,
    PublicationEventRead,
    PublicationValidationRead,
    PublicHotspotAdminRead,
    PublicHotspotCreate,
    PublicHotspotUpdate,
    PublicMediaAssetAdminRead,
    PublicMediaAssetCreate,
    PublicMediaAssetUpdate,
    PublishedChapterAdminRead,
    PublishedChapterCreate,
    PublishedChapterUpdate,
    PublishedPageAdminRead,
    PublishedPageCreate,
    PublishedPageUpdate,
    PublishedPanelAdminRead,
    PublishedPanelCreate,
    PublishedPanelUpdate,
    PublishedVolumeAdminRead,
    PublishedVolumeCreate,
    PublishedVolumeUpdate,
    PublishedWorkAdminRead,
    PublishedWorkCreate,
    PublishedWorkUpdate,
    ScheduleRequest,
    SetVisibilityRequest,
)
from app.schemas.public_reader import PublishedPageRead, PublishedWorkDetail
from app.services import curation
from app.services import public_reader_service as reader
from app.services.knowledge import slugify
from app.services.public_reader_service import publish_work_to_public_reader
from app.utils import Page, PageParams, apply_patch, get_or_404, page_params, paginate

router = APIRouter(prefix="/curation", tags=["curation"], dependencies=AUTHED)


def _unique_slug(session: Session, base: str, exclude_id: Optional[str] = None) -> str:
    base = slugify(base) or "untitled"
    candidate, i = base, 2
    while True:
        clash = session.exec(
            select(PublishedWork).where(PublishedWork.slug == candidate)
        ).first()
        if clash is None or clash.id == exclude_id:
            return candidate
        candidate, i = f"{base}-{i}", i + 1


# --- PublishedWork ---------------------------------------------------------


@router.get("/works", response_model=Page[PublishedWorkAdminRead])
def list_works(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    status_: Optional[PublishedStatus] = Query(default=None, alias="status"),
) -> Page[PublishedWorkAdminRead]:
    stmt = select(PublishedWork)
    if status_ is not None:
        stmt = stmt.where(PublishedWork.status == status_)
    stmt = stmt.order_by(PublishedWork.created_at.desc())
    items, total = paginate(session, stmt, params)
    return Page[PublishedWorkAdminRead](
        items=[PublishedWorkAdminRead.model_validate(w) for w in items],
        total=total, skip=params.skip, limit=params.limit,
    )


@router.get("/works/{work_id}", response_model=PublishedWorkAdminRead)
def get_work(work_id: str, session: Session = Depends(get_session)) -> PublishedWork:
    return get_or_404(session, PublishedWork, work_id, name="PublishedWork")


@router.post("/works", response_model=PublishedWorkAdminRead, status_code=201)
def create_work(
    payload: PublishedWorkCreate, session: Session = Depends(get_session)
) -> PublishedWork:
    data = payload.model_dump()
    data["slug"] = _unique_slug(session, payload.slug or payload.title)
    work = PublishedWork(**data, status=PublishedStatus.DRAFT)
    session.add(work)
    session.flush()
    curation.record_event(session, work, curation.PublicationAction.CREATED)
    session.commit()
    session.refresh(work)
    return work


@router.post("/works/from-work", response_model=PublishedWorkAdminRead, status_code=201)
def create_work_from_source(
    payload: CreateFromWorkRequest, session: Session = Depends(get_session)
) -> PublishedWork:
    try:
        work = publish_work_to_public_reader(session, payload.source_work_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return work


@router.patch("/works/{work_id}", response_model=PublishedWorkAdminRead)
def update_work(
    work_id: str, payload: PublishedWorkUpdate, session: Session = Depends(get_session)
) -> PublishedWork:
    work = get_or_404(session, PublishedWork, work_id, name="PublishedWork")
    data = payload.model_dump(exclude_unset=True)
    if "slug" in data and data["slug"]:
        data["slug"] = _unique_slug(session, data["slug"], exclude_id=work.id)
    for key, value in data.items():
        setattr(work, key, value)
    session.add(work)
    curation.record_event(session, work, curation.PublicationAction.UPDATED)
    session.commit()
    session.refresh(work)
    return work


@router.delete("/works/{work_id}", status_code=204, dependencies=ADMIN_ONLY)
def delete_work(work_id: str, session: Session = Depends(get_session)):
    work = get_or_404(session, PublishedWork, work_id, name="PublishedWork")
    session.delete(work)
    session.commit()


# --- lifecycle -------------------------------------------------------------


@router.get("/works/{work_id}/validate", response_model=PublicationValidationRead)
def validate_work(work_id: str, session: Session = Depends(get_session)) -> PublicationValidationRead:
    work = get_or_404(session, PublishedWork, work_id, name="PublishedWork")
    return PublicationValidationRead(**curation.validate_for_publication(session, work))


@router.get("/works/{work_id}/preview", response_model=PublishedWorkDetail)
def preview_work(work_id: str, session: Session = Depends(get_session)) -> PublishedWorkDetail:
    detail = reader.preview_work_detail(session, work_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Published work not found")
    return detail


@router.get("/works/{work_id}/events", response_model=list[PublicationEventRead])
def list_events(work_id: str, session: Session = Depends(get_session)) -> list[PublicationEventRead]:
    rows = session.exec(
        select(PublicationEvent)
        .where(PublicationEvent.published_work_id == work_id)
        .order_by(PublicationEvent.created_at.desc())
    ).all()
    return [PublicationEventRead.model_validate(e) for e in rows]


@router.get("/works/{work_id}/approvals", response_model=list[PublicationApprovalRead])
def list_approvals(work_id: str, session: Session = Depends(get_session)) -> list[PublicationApprovalRead]:
    rows = session.exec(
        select(PublicationApproval)
        .where(PublicationApproval.published_work_id == work_id)
        .order_by(PublicationApproval.created_at.desc())
    ).all()
    return [PublicationApprovalRead.model_validate(a) for a in rows]


@router.post("/works/{work_id}/schedule", response_model=PublishedWorkAdminRead)
def schedule_work(
    work_id: str, payload: ScheduleRequest, session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PublishedWork:
    work = get_or_404(session, PublishedWork, work_id, name="PublishedWork")
    curation.schedule(session, work, payload.publication_date, user=user, note=payload.note)
    session.commit()
    session.refresh(work)
    return work


@router.post("/works/{work_id}/visibility", response_model=PublishedWorkAdminRead)
def set_visibility(
    work_id: str, payload: SetVisibilityRequest, session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PublishedWork:
    work = get_or_404(session, PublishedWork, work_id, name="PublishedWork")
    curation.set_visibility(session, work, payload.status, user=user, note=payload.note)
    session.commit()
    session.refresh(work)
    return work


@router.post("/works/{work_id}/request-approval", response_model=PublicationApprovalRead, status_code=201)
def request_approval(
    work_id: str, session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PublicationApproval:
    work = get_or_404(session, PublishedWork, work_id, name="PublishedWork")
    approval = curation.request_approval(session, work, user=user)
    session.commit()
    session.refresh(approval)
    return approval


@router.post("/approvals/{approval_id}/approve", response_model=PublicationApprovalRead, dependencies=ADMIN_ONLY)
def approve_publication(
    approval_id: str, payload: ApprovalDecisionRequest, session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PublicationApproval:
    approval = get_or_404(session, PublicationApproval, approval_id, name="PublicationApproval")
    curation.decide_approval(session, approval, approve=True, user=user, note=payload.note)
    session.commit()
    session.refresh(approval)
    return approval


@router.post("/approvals/{approval_id}/reject", response_model=PublicationApprovalRead, dependencies=ADMIN_ONLY)
def reject_publication(
    approval_id: str, payload: ApprovalDecisionRequest, session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PublicationApproval:
    approval = get_or_404(session, PublicationApproval, approval_id, name="PublicationApproval")
    curation.decide_approval(session, approval, approve=False, user=user, note=payload.note)
    session.commit()
    session.refresh(approval)
    return approval


@router.post("/works/{work_id}/publish", response_model=PublishedWorkAdminRead, dependencies=ADMIN_ONLY)
def publish_work(
    work_id: str, session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PublishedWork:
    work = get_or_404(session, PublishedWork, work_id, name="PublishedWork")
    curation.publish(session, work, user=user)
    session.commit()
    session.refresh(work)
    return work


@router.post("/works/{work_id}/unpublish", response_model=PublishedWorkAdminRead, dependencies=ADMIN_ONLY)
def unpublish_work(
    work_id: str, payload: ApprovalDecisionRequest | None = None,
    session: Session = Depends(get_session), user: User = Depends(get_current_user),
) -> PublishedWork:
    work = get_or_404(session, PublishedWork, work_id, name="PublishedWork")
    curation.unpublish(session, work, user=user, note=payload.note if payload else None)
    session.commit()
    session.refresh(work)
    return work


# --- volumes / chapters / pages / panels -----------------------------------


@router.get("/works/{work_id}/volumes", response_model=list[PublishedVolumeAdminRead])
def list_volumes(work_id: str, session: Session = Depends(get_session)) -> list[PublishedVolumeAdminRead]:
    rows = session.exec(
        select(PublishedVolume).where(PublishedVolume.published_work_id == work_id)
        .order_by(PublishedVolume.volume_number)
    ).all()
    return [PublishedVolumeAdminRead.model_validate(v) for v in rows]


@router.post("/works/{work_id}/volumes", response_model=PublishedVolumeAdminRead, status_code=201)
def create_volume(
    work_id: str, payload: PublishedVolumeCreate, session: Session = Depends(get_session)
) -> PublishedVolume:
    get_or_404(session, PublishedWork, work_id, name="PublishedWork")
    volume = PublishedVolume(published_work_id=work_id, **payload.model_dump())
    session.add(volume)
    session.commit()
    session.refresh(volume)
    return volume


@router.patch("/volumes/{volume_id}", response_model=PublishedVolumeAdminRead)
def update_volume(
    volume_id: str, payload: PublishedVolumeUpdate, session: Session = Depends(get_session)
) -> PublishedVolume:
    volume = get_or_404(session, PublishedVolume, volume_id, name="PublishedVolume")
    apply_patch(volume, payload)
    session.add(volume)
    session.commit()
    session.refresh(volume)
    return volume


@router.delete("/volumes/{volume_id}", status_code=204, dependencies=ADMIN_ONLY)
def delete_volume(volume_id: str, session: Session = Depends(get_session)):
    volume = get_or_404(session, PublishedVolume, volume_id, name="PublishedVolume")
    session.delete(volume)
    session.commit()


@router.get("/volumes/{volume_id}/chapters", response_model=list[PublishedChapterAdminRead])
def list_chapters(volume_id: str, session: Session = Depends(get_session)) -> list[PublishedChapterAdminRead]:
    rows = session.exec(
        select(PublishedChapter).where(PublishedChapter.published_volume_id == volume_id)
        .order_by(PublishedChapter.chapter_number)
    ).all()
    return [PublishedChapterAdminRead.model_validate(c) for c in rows]


@router.post("/volumes/{volume_id}/chapters", response_model=PublishedChapterAdminRead, status_code=201)
def create_chapter(
    volume_id: str, payload: PublishedChapterCreate, session: Session = Depends(get_session)
) -> PublishedChapter:
    get_or_404(session, PublishedVolume, volume_id, name="PublishedVolume")
    chapter = PublishedChapter(published_volume_id=volume_id, **payload.model_dump())
    session.add(chapter)
    session.commit()
    session.refresh(chapter)
    return chapter


@router.patch("/chapters/{chapter_id}", response_model=PublishedChapterAdminRead)
def update_chapter(
    chapter_id: str, payload: PublishedChapterUpdate, session: Session = Depends(get_session)
) -> PublishedChapter:
    chapter = get_or_404(session, PublishedChapter, chapter_id, name="PublishedChapter")
    apply_patch(chapter, payload)
    session.add(chapter)
    session.commit()
    session.refresh(chapter)
    return chapter


@router.delete("/chapters/{chapter_id}", status_code=204, dependencies=ADMIN_ONLY)
def delete_chapter(chapter_id: str, session: Session = Depends(get_session)):
    chapter = get_or_404(session, PublishedChapter, chapter_id, name="PublishedChapter")
    session.delete(chapter)
    session.commit()


@router.get("/chapters/{chapter_id}/pages", response_model=list[PublishedPageAdminRead])
def list_pages(chapter_id: str, session: Session = Depends(get_session)) -> list[PublishedPageAdminRead]:
    rows = session.exec(
        select(PublishedPage).where(PublishedPage.published_chapter_id == chapter_id)
        .order_by(PublishedPage.page_number)
    ).all()
    return [PublishedPageAdminRead.model_validate(p) for p in rows]


@router.post("/chapters/{chapter_id}/pages", response_model=PublishedPageAdminRead, status_code=201)
def create_page(
    chapter_id: str, payload: PublishedPageCreate, session: Session = Depends(get_session)
) -> PublishedPage:
    get_or_404(session, PublishedChapter, chapter_id, name="PublishedChapter")
    page = PublishedPage(published_chapter_id=chapter_id, **payload.model_dump())
    session.add(page)
    session.commit()
    session.refresh(page)
    return page


@router.patch("/pages/{page_id}", response_model=PublishedPageAdminRead)
def update_page(
    page_id: str, payload: PublishedPageUpdate, session: Session = Depends(get_session)
) -> PublishedPage:
    page = get_or_404(session, PublishedPage, page_id, name="PublishedPage")
    apply_patch(page, payload)
    session.add(page)
    session.commit()
    session.refresh(page)
    return page


@router.delete("/pages/{page_id}", status_code=204, dependencies=ADMIN_ONLY)
def delete_page(page_id: str, session: Session = Depends(get_session)):
    page = get_or_404(session, PublishedPage, page_id, name="PublishedPage")
    session.delete(page)
    session.commit()


@router.get("/pages/{page_id}/preview", response_model=PublishedPageRead)
def preview_page(page_id: str, session: Session = Depends(get_session)) -> PublishedPageRead:
    page = reader.preview_page(session, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


@router.get("/pages/{page_id}/panels", response_model=list[PublishedPanelAdminRead])
def list_panels(page_id: str, session: Session = Depends(get_session)) -> list[PublishedPanelAdminRead]:
    rows = session.exec(
        select(PublishedPanel).where(PublishedPanel.published_page_id == page_id)
        .order_by(PublishedPanel.reading_order)
    ).all()
    return [PublishedPanelAdminRead.model_validate(p) for p in rows]


@router.post("/pages/{page_id}/panels", response_model=PublishedPanelAdminRead, status_code=201)
def create_panel(
    page_id: str, payload: PublishedPanelCreate, session: Session = Depends(get_session)
) -> PublishedPanel:
    get_or_404(session, PublishedPage, page_id, name="PublishedPage")
    panel = PublishedPanel(published_page_id=page_id, **payload.model_dump())
    session.add(panel)
    session.commit()
    session.refresh(panel)
    return panel


@router.patch("/panels/{panel_id}", response_model=PublishedPanelAdminRead)
def update_panel(
    panel_id: str, payload: PublishedPanelUpdate, session: Session = Depends(get_session)
) -> PublishedPanel:
    panel = get_or_404(session, PublishedPanel, panel_id, name="PublishedPanel")
    apply_patch(panel, payload)
    session.add(panel)
    session.commit()
    session.refresh(panel)
    return panel


@router.delete("/panels/{panel_id}", status_code=204)
def delete_panel(panel_id: str, session: Session = Depends(get_session)):
    panel = get_or_404(session, PublishedPanel, panel_id, name="PublishedPanel")
    session.delete(panel)
    session.commit()


# --- public media ----------------------------------------------------------


@router.get("/media", response_model=list[PublicMediaAssetAdminRead])
def list_media(session: Session = Depends(get_session)) -> list[PublicMediaAssetAdminRead]:
    rows = session.exec(
        select(PublicMediaAsset).order_by(PublicMediaAsset.created_at.desc())
    ).all()
    return [PublicMediaAssetAdminRead.model_validate(m) for m in rows]


@router.post("/media", response_model=PublicMediaAssetAdminRead, status_code=201)
def create_media(
    payload: PublicMediaAssetCreate, session: Session = Depends(get_session)
) -> PublicMediaAsset:
    media = PublicMediaAsset(**payload.model_dump())
    session.add(media)
    session.commit()
    session.refresh(media)
    return media


@router.patch("/media/{media_id}", response_model=PublicMediaAssetAdminRead)
def update_media(
    media_id: str, payload: PublicMediaAssetUpdate, session: Session = Depends(get_session)
) -> PublicMediaAsset:
    media = get_or_404(session, PublicMediaAsset, media_id, name="PublicMediaAsset")
    apply_patch(media, payload)
    session.add(media)
    session.commit()
    session.refresh(media)
    return media


@router.delete("/media/{media_id}", status_code=204, dependencies=ADMIN_ONLY)
def delete_media(media_id: str, session: Session = Depends(get_session)):
    media = get_or_404(session, PublicMediaAsset, media_id, name="PublicMediaAsset")
    session.delete(media)
    session.commit()


# --- hotspots --------------------------------------------------------------


@router.get("/pages/{page_id}/hotspots", response_model=list[PublicHotspotAdminRead])
def list_hotspots(page_id: str, session: Session = Depends(get_session)) -> list[PublicHotspotAdminRead]:
    rows = session.exec(
        select(PublicHotspot).where(PublicHotspot.published_page_id == page_id)
    ).all()
    return [PublicHotspotAdminRead.model_validate(h) for h in rows]


@router.post("/pages/{page_id}/hotspots", response_model=PublicHotspotAdminRead, status_code=201)
def create_hotspot(
    page_id: str, payload: PublicHotspotCreate, session: Session = Depends(get_session)
) -> PublicHotspot:
    get_or_404(session, PublishedPage, page_id, name="PublishedPage")
    if payload.published_panel_id is not None:
        get_or_404(session, PublishedPanel, payload.published_panel_id, name="PublishedPanel")
    hotspot = PublicHotspot(published_page_id=page_id, **payload.model_dump())
    session.add(hotspot)
    session.commit()
    session.refresh(hotspot)
    return hotspot


@router.patch("/hotspots/{hotspot_id}", response_model=PublicHotspotAdminRead)
def update_hotspot(
    hotspot_id: str, payload: PublicHotspotUpdate, session: Session = Depends(get_session)
) -> PublicHotspot:
    hotspot = get_or_404(session, PublicHotspot, hotspot_id, name="PublicHotspot")
    apply_patch(hotspot, payload)
    session.add(hotspot)
    session.commit()
    session.refresh(hotspot)
    return hotspot


@router.delete("/hotspots/{hotspot_id}", status_code=204)
def delete_hotspot(hotspot_id: str, session: Session = Depends(get_session)):
    hotspot = get_or_404(session, PublicHotspot, hotspot_id, name="PublicHotspot")
    session.delete(hotspot)
    session.commit()


# --- controlled hand-off ---------------------------------------------------


@router.post("/handoff/page", response_model=PublishedPageAdminRead, status_code=201)
def handoff_page(
    payload: PageHandoffRequest, session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PublishedPage:
    page = curation.hand_off_page(session, payload, user=user)
    session.commit()
    session.refresh(page)
    return page
