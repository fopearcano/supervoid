"""Public reader service.

Builds the public, read-only projection consumed by the SUPERVOID Graphic
Novel Webviewer, and provides the publication bridge that prepares a private
``Work`` for public reading.

Two invariants enforced here:

1. **Visibility** — content is only reachable when its owning ``PublishedWork``
   is ``PUBLISHED`` (listed) or ``UNLISTED`` (by-slug only). Deep object ids
   for ``DRAFT`` / ``ARCHIVED`` works resolve to nothing.
2. **Public-safe only** — nothing here reads or returns private editorial data.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import (
    Author,
    PublicHotspot,
    PublicMediaAsset,
    PublishedChapter,
    PublishedPage,
    PublishedPanel,
    PublishedStatus,
    PublishedVolume,
    PublishedWork,
    Work,
)
from app.schemas.public_reader import (
    PublicHotspotRead,
    PublicMediaAssetRead,
    PublishedChapterRead,
    PublishedChapterSummary,
    PublishedPageRead,
    PublishedPanelRead,
    PublishedVolumeRead,
    PublishedWorkDetail,
    PublishedWorkSummary,
)
from app.services.knowledge import slugify

# Reachable by direct slug/id; only PUBLISHED is enumerated in listings.
_VISIBLE = (PublishedStatus.PUBLISHED, PublishedStatus.UNLISTED)

MediaCache = dict[str, Optional[PublicMediaAssetRead]]


# --- media resolution ------------------------------------------------------


def _media_read(
    session: Session, media_id: Optional[str], cache: MediaCache
) -> Optional[PublicMediaAssetRead]:
    if not media_id:
        return None
    if media_id in cache:
        return cache[media_id]
    asset = session.get(PublicMediaAsset, media_id)
    result = (
        PublicMediaAssetRead.model_validate(asset)
        if asset is not None and asset.public_visibility
        else None
    )
    cache[media_id] = result
    return result


def get_media(session: Session, media_id: str) -> Optional[PublicMediaAssetRead]:
    return _media_read(session, media_id, {})


# --- visibility helpers ----------------------------------------------------


def _get_visible_work(session: Session, slug: str) -> Optional[PublishedWork]:
    work = session.exec(
        select(PublishedWork).where(PublishedWork.slug == slug)
    ).first()
    if work is None or work.status not in _VISIBLE:
        return None
    return work


def _chapter_visible(session: Session, chapter: PublishedChapter) -> bool:
    volume = session.get(PublishedVolume, chapter.published_volume_id)
    if volume is None:
        return False
    work = session.get(PublishedWork, volume.published_work_id)
    return work is not None and work.status in _VISIBLE


def _page_count(session: Session, chapter_id: str) -> int:
    return session.exec(
        select(func.count())
        .select_from(PublishedPage)
        .where(PublishedPage.published_chapter_id == chapter_id)
    ).one()


# --- read builders ---------------------------------------------------------


def _chapter_summary(
    session: Session, chapter: PublishedChapter
) -> PublishedChapterSummary:
    return PublishedChapterSummary(
        id=chapter.id,
        title=chapter.title,
        chapter_number=chapter.chapter_number,
        public_description=chapter.public_description,
        page_count=_page_count(session, chapter.id),
    )


def _volume_read(
    session: Session, volume: PublishedVolume, cache: MediaCache
) -> PublishedVolumeRead:
    return PublishedVolumeRead(
        id=volume.id,
        title=volume.title,
        volume_number=volume.volume_number,
        public_description=volume.public_description,
        cover_image=volume.cover_image,
        publication_date=volume.publication_date,
        music_track=_media_read(session, volume.music_track_id, cache),
        chapters=[_chapter_summary(session, ch) for ch in volume.chapters],
    )


def _hotspot_read(
    session: Session, hotspot: PublicHotspot, cache: MediaCache
) -> PublicHotspotRead:
    return PublicHotspotRead(
        id=hotspot.id,
        type=hotspot.type,
        x=hotspot.x,
        y=hotspot.y,
        width=hotspot.width,
        height=hotspot.height,
        title=hotspot.title,
        content=hotspot.content,
        target_url=hotspot.target_url,
        audio_track=_media_read(session, hotspot.audio_track_id, cache),
        video=_media_read(session, hotspot.video_id, cache),
    )


def _panel_read(
    session: Session, panel: PublishedPanel, cache: MediaCache
) -> PublishedPanelRead:
    return PublishedPanelRead(
        id=panel.id,
        panel_number=panel.panel_number,
        reading_order=panel.reading_order,
        x=panel.x,
        y=panel.y,
        width=panel.width,
        height=panel.height,
        focus_x=panel.focus_x,
        focus_y=panel.focus_y,
        focus_width=panel.focus_width,
        focus_height=panel.focus_height,
        transition=panel.transition,
        transition_duration_ms=panel.transition_duration_ms,
        caption=panel.caption,
        alt_text=panel.alt_text,
        audio_track=_media_read(session, panel.audio_track_id, cache),
        video=_media_read(session, panel.video_id, cache),
        hotspots=[_hotspot_read(session, h, cache) for h in panel.hotspots],
    )


def _page_read(
    session: Session, page: PublishedPage, cache: MediaCache
) -> PublishedPageRead:
    return PublishedPageRead(
        id=page.id,
        page_number=page.page_number,
        image_path=page.image_path,
        alt_text=page.alt_text,
        width=page.width,
        height=page.height,
        music_track=_media_read(session, page.music_track_id, cache),
        video_overlay=_media_read(session, page.video_overlay_id, cache),
        # Page-level hotspots are those not bound to a panel; panel hotspots
        # travel inside their panel for cinematic mode.
        hotspots=[
            _hotspot_read(session, h, cache)
            for h in page.hotspots
            if h.published_panel_id is None
        ],
        panels=[_panel_read(session, p, cache) for p in page.panels],
    )


# --- public queries --------------------------------------------------------


def list_published_works(session: Session) -> list[PublishedWorkSummary]:
    stmt = (
        select(PublishedWork)
        .where(PublishedWork.status == PublishedStatus.PUBLISHED)
        .order_by(PublishedWork.publication_date.desc(), PublishedWork.title)
    )
    return [PublishedWorkSummary.model_validate(w) for w in session.exec(stmt).all()]


def _work_detail_read(session: Session, work: PublishedWork) -> PublishedWorkDetail:
    cache: MediaCache = {}
    return PublishedWorkDetail(
        id=work.id,
        slug=work.slug,
        title=work.title,
        subtitle=work.subtitle,
        public_synopsis=work.public_synopsis,
        cover_image=work.cover_image,
        status=work.status,
        publication_date=work.publication_date,
        author_credit=work.author_credit,
        artist_credit=work.artist_credit,
        tags=work.tags,
        music_track=_media_read(session, work.music_track_id, cache),
        video_intro=_media_read(session, work.video_intro_id, cache),
        volumes=[_volume_read(session, v, cache) for v in work.volumes],
    )


def get_work_detail(session: Session, slug: str) -> Optional[PublishedWorkDetail]:
    work = _get_visible_work(session, slug)
    if work is None:
        return None
    return _work_detail_read(session, work)


# --- private preview (admin) -----------------------------------------------
# Build the EXACT public representation for a work/page regardless of status, so
# a curator can preview a DRAFT before it is published. These bypass the
# visibility gate by design and are only ever reached through the private,
# authenticated curation API — never the public router.


def preview_work_detail(
    session: Session, work_id: str
) -> Optional[PublishedWorkDetail]:
    work = session.get(PublishedWork, work_id)
    if work is None:
        return None
    return _work_detail_read(session, work)


def preview_page(session: Session, page_id: str) -> Optional[PublishedPageRead]:
    page = session.get(PublishedPage, page_id)
    if page is None:
        return None
    return _page_read(session, page, {})


def list_volumes_for_work(
    session: Session, slug: str
) -> Optional[list[PublishedVolumeRead]]:
    work = _get_visible_work(session, slug)
    if work is None:
        return None
    cache: MediaCache = {}
    return [_volume_read(session, v, cache) for v in work.volumes]


def list_chapters_for_volume(
    session: Session, volume_id: str
) -> Optional[list[PublishedChapterRead]]:
    volume = session.get(PublishedVolume, volume_id)
    if volume is None:
        return None
    work = session.get(PublishedWork, volume.published_work_id)
    if work is None or work.status not in _VISIBLE:
        return None
    cache: MediaCache = {}
    chapters: list[PublishedChapterRead] = []
    for ch in volume.chapters:
        chapters.append(
            PublishedChapterRead(
                id=ch.id,
                title=ch.title,
                chapter_number=ch.chapter_number,
                public_description=ch.public_description,
                page_count=_page_count(session, ch.id),
                music_track=_media_read(session, ch.music_track_id, cache),
                video_intro=_media_read(session, ch.video_intro_id, cache),
            )
        )
    return chapters


def list_pages_for_chapter(
    session: Session, chapter_id: str
) -> Optional[list[PublishedPageRead]]:
    chapter = session.get(PublishedChapter, chapter_id)
    if chapter is None or not _chapter_visible(session, chapter):
        return None
    cache: MediaCache = {}
    return [_page_read(session, p, cache) for p in chapter.pages]


def get_page(session: Session, page_id: str) -> Optional[PublishedPageRead]:
    page = session.get(PublishedPage, page_id)
    if page is None:
        return None
    chapter = session.get(PublishedChapter, page.published_chapter_id)
    if chapter is None or not _chapter_visible(session, chapter):
        return None
    return _page_read(session, page, {})


def list_hotspots_for_page(
    session: Session, page_id: str
) -> Optional[list[PublicHotspotRead]]:
    page = session.get(PublishedPage, page_id)
    if page is None:
        return None
    chapter = session.get(PublishedChapter, page.published_chapter_id)
    if chapter is None or not _chapter_visible(session, chapter):
        return None
    cache: MediaCache = {}
    return [_hotspot_read(session, h, cache) for h in page.hotspots]


# --- publication bridge ----------------------------------------------------

# What the bridge cannot infer from the private system and must be curated by
# hand after the shell is created. Documented here and in docs/PUBLIC_VIEWER.md.
PUBLISH_MANUAL_STEPS: tuple[str, ...] = (
    "Set status to PUBLISHED and a publication_date when ready to go live.",
    "Upload/curate cover_image and artist_credit.",
    "Create PublishedVolume / PublishedChapter / PublishedPage records.",
    "Attach page image PublicMediaAssets (no private files are ever copied).",
    "Add background music / intro video media and curated public hotspots.",
)


def _unique_slug(
    session: Session, base: str, exclude_id: Optional[str] = None
) -> str:
    base = base or "untitled"
    candidate, i = base, 2
    while True:
        clash = session.exec(
            select(PublishedWork).where(PublishedWork.slug == candidate)
        ).first()
        if clash is None or clash.id == exclude_id:
            return candidate
        candidate, i = f"{base}-{i}", i + 1


def publish_work_to_public_reader(session: Session, work_id: str) -> PublishedWork:
    """Create or update a ``PublishedWork`` shell from a private ``Work``.

    Copies *only* public metadata (title, subtitle, synopsis → public_synopsis,
    genre → tags, author name → author_credit). It NEVER copies internal pitch,
    target audience, contracts, rights, editorial notes, workflow, production
    status, or private attachments. The remaining steps in
    ``PUBLISH_MANUAL_STEPS`` are intentionally manual — this is a bridge, not a
    CMS. Idempotent per source work.
    """
    work = session.get(Work, work_id)
    if work is None:
        raise ValueError(f"Work {work_id!r} not found")

    author = session.get(Author, work.author_id) if work.author_id else None
    existing = session.exec(
        select(PublishedWork).where(PublishedWork.source_work_id == work_id)
    ).first()

    pub = existing or PublishedWork(
        source_work_id=work_id,
        slug=_unique_slug(session, slugify(work.title)),
        status=PublishedStatus.DRAFT,  # curator flips to PUBLISHED by hand
    )

    # Public metadata only.
    pub.title = work.title
    pub.subtitle = work.subtitle
    pub.public_synopsis = work.synopsis
    pub.author_credit = author.full_name if author is not None else None
    pub.tags = [work.genre] if work.genre else []

    session.add(pub)
    session.commit()
    session.refresh(pub)
    return pub
