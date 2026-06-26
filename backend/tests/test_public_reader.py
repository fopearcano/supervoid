from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import (
    Author,
    HotspotType,
    MediaAssetType,
    PublicHotspot,
    PublicMediaAsset,
    PublishedChapter,
    PublishedPage,
    PublishedStatus,
    PublishedVolume,
    PublishedWork,
    Work,
)
from app.services.public_reader_service import publish_work_to_public_reader

# Tokens that must never appear anywhere in a public response body.
_PRIVATE_TOKENS = (
    "source_work_id",
    "internal_pitch",
    "target_audience",
    "contract",
    "royalty",
    "rights",
    "workflow",
    "hashed_password",
)


def _assert_no_private(payload) -> None:
    blob = json.dumps(payload).lower()
    leaked = [t for t in _PRIVATE_TOKENS if t in blob]
    assert not leaked, f"private tokens leaked: {leaked}"


def _make_published(
    session: Session,
    *,
    slug: str = "demo-gn",
    status: PublishedStatus = PublishedStatus.PUBLISHED,
    with_children: bool = True,
) -> PublishedWork:
    music = PublicMediaAsset(
        type=MediaAssetType.AUDIO, title="Theme", file_path="/public/demo/audio/theme.mp3"
    )
    hidden = PublicMediaAsset(
        type=MediaAssetType.AUDIO,
        title="Hidden",
        file_path="/public/demo/audio/secret.mp3",
        public_visibility=False,
    )
    session.add_all([music, hidden])
    session.commit()
    session.refresh(music)
    session.refresh(hidden)

    work = PublishedWork(
        slug=slug,
        title="Demo Graphic Novel",
        subtitle="A test",
        public_synopsis="Public synopsis.",
        cover_image="/public/demo/covers/demo.svg",
        status=status,
        author_credit="A. Author",
        tags=["noir", "test"],
        music_track_id=music.id,
    )
    session.add(work)
    session.commit()
    session.refresh(work)

    if not with_children:
        return work

    volume = PublishedVolume(
        published_work_id=work.id, title="Vol 1", volume_number=1
    )
    session.add(volume)
    session.commit()
    session.refresh(volume)

    chapter = PublishedChapter(
        published_volume_id=volume.id,
        title="Ch 1",
        chapter_number=1,
        music_track_id=music.id,
    )
    session.add(chapter)
    session.commit()
    session.refresh(chapter)

    page = PublishedPage(
        published_chapter_id=chapter.id,
        page_number=1,
        image_path="/public/demo/pages/page-001.svg",
        alt_text="page 1",
    )
    session.add(page)
    session.commit()
    session.refresh(page)

    session.add(
        PublicHotspot(
            published_page_id=page.id,
            type=HotspotType.INFO,
            x=10, y=10, width=20, height=10,
            title="Note",
            content="A public note.",
        )
    )
    session.commit()
    # store the hidden id on the object for the visibility test
    work._hidden_media_id = hidden.id  # type: ignore[attr-defined]
    return work


# --- listing & visibility --------------------------------------------------


def test_list_returns_only_published(anon_client: TestClient, session: Session) -> None:
    _make_published(session, slug="live", status=PublishedStatus.PUBLISHED)
    _make_published(session, slug="hidden-draft", status=PublishedStatus.DRAFT)

    r = anon_client.get("/public/works")
    assert r.status_code == 200
    slugs = {w["slug"] for w in r.json()}
    assert slugs == {"live"}
    _assert_no_private(r.json())


def test_draft_not_reachable_by_slug(anon_client: TestClient, session: Session) -> None:
    _make_published(session, slug="draft", status=PublishedStatus.DRAFT)
    assert anon_client.get("/public/works/draft").status_code == 404


def test_unlisted_reachable_by_slug_but_not_listed(
    anon_client: TestClient, session: Session
) -> None:
    _make_published(session, slug="secret", status=PublishedStatus.UNLISTED)
    assert anon_client.get("/public/works").json() == []
    assert anon_client.get("/public/works/secret").status_code == 200


# --- detail & navigation ---------------------------------------------------


def test_detail_and_navigation(anon_client: TestClient, session: Session) -> None:
    _make_published(session, slug="demo")

    detail = anon_client.get("/public/works/demo")
    assert detail.status_code == 200
    body = detail.json()
    assert body["title"] == "Demo Graphic Novel"
    assert body["tags"] == ["noir", "test"]
    assert "source_work_id" not in body
    assert len(body["volumes"]) == 1
    _assert_no_private(body)

    volume_id = body["volumes"][0]["id"]
    chapters = anon_client.get(f"/public/volumes/{volume_id}/chapters").json()
    assert len(chapters) == 1
    assert chapters[0]["music_track"]["file_path"].endswith("theme.mp3")

    chapter_id = chapters[0]["id"]
    pages = anon_client.get(f"/public/chapters/{chapter_id}/pages").json()
    assert len(pages) == 1
    assert pages[0]["hotspots"][0]["title"] == "Note"

    page_id = pages[0]["id"]
    assert anon_client.get(f"/public/pages/{page_id}").status_code == 200
    hotspots = anon_client.get(f"/public/pages/{page_id}/hotspots").json()
    assert len(hotspots) == 1


def test_unpublished_deep_ids_are_not_reachable(
    anon_client: TestClient, session: Session
) -> None:
    work = _make_published(session, slug="draft2", status=PublishedStatus.DRAFT)
    # Walk the ORM to reach the (unpublished) volume/chapter/page ids.
    vol = work.volumes[0]
    ch = vol.chapters[0]
    page = ch.pages[0]
    assert anon_client.get(f"/public/volumes/{vol.id}/chapters").status_code == 404
    assert anon_client.get(f"/public/chapters/{ch.id}/pages").status_code == 404
    assert anon_client.get(f"/public/pages/{page.id}").status_code == 404
    assert anon_client.get(f"/public/pages/{page.id}/hotspots").status_code == 404


# --- media -----------------------------------------------------------------


def test_media_visibility(anon_client: TestClient, session: Session) -> None:
    work = _make_published(session, slug="media-demo")
    hidden_id = work._hidden_media_id  # type: ignore[attr-defined]
    assert anon_client.get(f"/public/media/{hidden_id}").status_code == 404


# --- read-only -------------------------------------------------------------


def test_public_api_is_read_only(anon_client: TestClient) -> None:
    assert anon_client.post("/public/works", json={}).status_code == 405
    assert anon_client.delete("/public/works/anything").status_code == 405


def test_public_routes_not_under_api(anon_client: TestClient) -> None:
    # The public surface lives at /public, never under the private /api prefix.
    assert anon_client.get("/api/public/works").status_code == 404


# --- publication bridge ----------------------------------------------------


def test_publish_bridge_copies_only_public_metadata(session: Session) -> None:
    author = Author(full_name="Jane Maker")
    session.add(author)
    session.commit()
    session.refresh(author)

    work = Work(
        title="Private Project",
        subtitle="sub",
        synopsis="Public-facing synopsis.",
        genre="Noir",
        internal_pitch="SECRET internal pitch — never publish.",
        target_audience="SECRET audience note.",
        author_id=author.id,
    )
    session.add(work)
    session.commit()
    session.refresh(work)

    pub = publish_work_to_public_reader(session, work.id)
    assert pub.title == "Private Project"
    assert pub.public_synopsis == "Public-facing synopsis."
    assert pub.tags == ["Noir"]
    assert pub.author_credit == "Jane Maker"
    assert pub.status == PublishedStatus.DRAFT  # curator publishes by hand
    # The public model has no concept of these private fields at all.
    assert not hasattr(pub, "internal_pitch")
    assert not hasattr(pub, "target_audience")

    # Idempotent per source work.
    pub2 = publish_work_to_public_reader(session, work.id)
    assert pub2.id == pub.id


# --- public Bookshop catalogue ---------------------------------------------


def test_catalogue_lists_only_published_for_sale(
    session: Session, anon_client: TestClient
) -> None:
    # published + for sale -> appears
    a = _make_published(session, slug="for-sale-gn", with_children=False)
    a.for_sale = True
    a.price_cents = 1500
    a.currency = "EUR"
    a.buy_url = "https://example.test/buy"
    a.format_label = "Paperback · 120pp"
    # published but NOT for sale -> excluded
    b = _make_published(session, slug="not-for-sale-gn", with_children=False)
    b.for_sale = False
    # draft + for sale -> excluded (public/private isolation holds)
    c = _make_published(
        session, slug="draft-for-sale", status=PublishedStatus.DRAFT, with_children=False
    )
    c.for_sale = True
    c.price_cents = 999
    session.add_all([a, b, c])
    session.commit()

    items = anon_client.get("/public/catalogue").json()
    assert {i["slug"] for i in items} == {"for-sale-gn"}
    item = items[0]
    assert item["price_cents"] == 1500
    assert item["currency"] == "EUR"
    assert item["buy_url"] == "https://example.test/buy"
    assert item["format_label"] == "Paperback · 120pp"
    _assert_no_private(items)
