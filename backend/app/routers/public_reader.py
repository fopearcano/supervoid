"""Public, read-only API for the SUPERVOID Graphic Novel Webviewer.

Mounted at ``/public`` (NOT under the private ``/api`` prefix) and intentionally
unauthenticated and GET-only. It exposes only the published projection built by
``public_reader_service`` — no private editorial data is reachable from here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.schemas.public_reader import (
    PublicHotspotRead,
    PublicMediaAssetRead,
    PublishedChapterRead,
    PublishedPageRead,
    PublishedVolumeRead,
    PublishedWorkDetail,
    PublishedWorkSummary,
)
from app.services import public_reader_service as reader

router = APIRouter(prefix="/public", tags=["public-reader"])


@router.get("/works", response_model=list[PublishedWorkSummary], summary="List published works")
def list_works(session: Session = Depends(get_session)) -> list[PublishedWorkSummary]:
    return reader.list_published_works(session)


@router.get("/works/{slug}", response_model=PublishedWorkDetail, summary="Published work detail")
def get_work(slug: str, session: Session = Depends(get_session)) -> PublishedWorkDetail:
    detail = reader.get_work_detail(session, slug)
    if detail is None:
        raise HTTPException(status_code=404, detail="Published work not found")
    return detail


@router.get(
    "/works/{slug}/volumes",
    response_model=list[PublishedVolumeRead],
    summary="Volumes of a published work",
)
def list_volumes(slug: str, session: Session = Depends(get_session)) -> list[PublishedVolumeRead]:
    volumes = reader.list_volumes_for_work(session, slug)
    if volumes is None:
        raise HTTPException(status_code=404, detail="Published work not found")
    return volumes


@router.get(
    "/volumes/{volume_id}/chapters",
    response_model=list[PublishedChapterRead],
    summary="Chapters of a volume",
)
def list_chapters(
    volume_id: str, session: Session = Depends(get_session)
) -> list[PublishedChapterRead]:
    chapters = reader.list_chapters_for_volume(session, volume_id)
    if chapters is None:
        raise HTTPException(status_code=404, detail="Volume not found")
    return chapters


@router.get(
    "/chapters/{chapter_id}/pages",
    response_model=list[PublishedPageRead],
    summary="Pages of a chapter (with hotspots and resolved media)",
)
def list_pages(
    chapter_id: str, session: Session = Depends(get_session)
) -> list[PublishedPageRead]:
    pages = reader.list_pages_for_chapter(session, chapter_id)
    if pages is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return pages


@router.get("/pages/{page_id}", response_model=PublishedPageRead, summary="A single page")
def get_page(page_id: str, session: Session = Depends(get_session)) -> PublishedPageRead:
    page = reader.get_page(session, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


@router.get(
    "/pages/{page_id}/hotspots",
    response_model=list[PublicHotspotRead],
    summary="Curated public hotspots on a page",
)
def list_hotspots(
    page_id: str, session: Session = Depends(get_session)
) -> list[PublicHotspotRead]:
    hotspots = reader.list_hotspots_for_page(session, page_id)
    if hotspots is None:
        raise HTTPException(status_code=404, detail="Page not found")
    return hotspots


@router.get("/media/{media_id}", response_model=PublicMediaAssetRead, summary="A public media asset")
def get_media(media_id: str, session: Session = Depends(get_session)) -> PublicMediaAssetRead:
    media = reader.get_media(session, media_id)
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")
    return media
