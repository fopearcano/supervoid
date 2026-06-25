"""Private curation CMS + controlled hand-off + public/private separation.

The headline guarantee: unpublished or private data is never reachable through
``/public``. Also covers the gated publication lifecycle (validate → approve →
publish), unpublish-preserves-source, the explicit public-derivative hand-off,
licence/provenance validation, preview, and public cinematic panels.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session


# --- helpers ---------------------------------------------------------------


def _work(client: TestClient, title: str = "Curated Work") -> dict:
    author = client.post("/api/authors", json={"full_name": "A"}).json()["id"]
    r = client.post("/api/works", json={"title": title, "author_id": author})
    assert r.status_code == 201, r.text
    return r.json()


def _published_work(client: TestClient, **over) -> dict:
    payload = {"title": "The Silent Workshop", "author_credit": "Saoirse Carrick"}
    payload.update(over)
    r = client.post("/api/curation/works", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _structure(client: TestClient, work_id: str, *, image_path: str = "/public/demo/p1.svg") -> dict:
    vol = client.post(
        f"/api/curation/works/{work_id}/volumes", json={"title": "V1", "volume_number": 1}
    ).json()
    ch = client.post(
        f"/api/curation/volumes/{vol['id']}/chapters", json={"title": "C1", "chapter_number": 1}
    ).json()
    pg = client.post(
        f"/api/curation/chapters/{ch['id']}/pages",
        json={"page_number": 1, "image_path": image_path},
    ).json()
    return {"volume": vol, "chapter": ch, "page": pg}


def _media(client: TestClient, file_path: str = "/public/derivatives/page-1.webp") -> dict:
    r = client.post(
        "/api/curation/media",
        json={"type": "image", "title": "Public derivative", "file_path": file_path},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _approve_and_publish(client: TestClient, work_id: str) -> None:
    approval = client.post(f"/api/curation/works/{work_id}/request-approval").json()
    client.post(f"/api/curation/approvals/{approval['id']}/approve", json={})
    r = client.post(f"/api/curation/works/{work_id}/publish")
    assert r.status_code == 200, r.text


def _gn_page(session: Session, work_id: str) -> str:
    """A minimal private GraphicNovelPage with one panel, returning its id."""
    from app.models import (
        GraphicNovelChapter,
        GraphicNovelPage,
        GraphicNovelPanel,
        GraphicNovelProduction,
        GraphicNovelSequence,
        GraphicNovelVolume,
    )

    prod = GraphicNovelProduction(work_id=work_id, volume_number=1)
    session.add(prod)
    session.flush()
    vol = GraphicNovelVolume(production_id=prod.id, volume_number=1)
    session.add(vol)
    session.flush()
    ch = GraphicNovelChapter(volume_id=vol.id, chapter_number=1)
    session.add(ch)
    session.flush()
    seq = GraphicNovelSequence(chapter_id=ch.id, sequence_number=1)
    session.add(seq)
    session.flush()
    page = GraphicNovelPage(sequence_id=seq.id, page_number=1)
    session.add(page)
    session.flush()
    session.add(GraphicNovelPanel(
        page_id=page.id, panel_number=1, position=0,
        x=0.1, y=0.1, width=0.8, height=0.4, dialogue="Hello.",
    ))
    session.commit()
    return page.id


# === public/private separation: the headline guarantee =====================


def test_draft_work_is_invisible_through_public(client: TestClient, anon_client: TestClient) -> None:
    work = _published_work(client)  # DRAFT by default
    s = _structure(client, work["id"])

    # Not listed, not retrievable by slug, deep ids resolve to nothing.
    listed = anon_client.get("/public/works").json()
    assert work["slug"] not in {w["slug"] for w in listed}
    assert anon_client.get(f"/public/works/{work['slug']}").status_code == 404
    assert anon_client.get(f"/public/volumes/{s['volume']['id']}/chapters").status_code == 404
    assert anon_client.get(f"/public/chapters/{s['chapter']['id']}/pages").status_code == 404
    assert anon_client.get(f"/public/pages/{s['page']['id']}").status_code == 404


def test_publish_then_visible_then_unpublish_hides_but_keeps_source(
    client: TestClient, anon_client: TestClient
) -> None:
    work = _published_work(client)
    s = _structure(client, work["id"])
    _approve_and_publish(client, work["id"])

    # Now visible publicly.
    assert work["slug"] in {w["slug"] for w in anon_client.get("/public/works").json()}
    assert anon_client.get(f"/public/works/{work['slug']}").status_code == 200
    assert anon_client.get(f"/public/pages/{s['page']['id']}").status_code == 200

    # Unpublish → invisible again, but the projection rows still exist privately.
    assert client.post(f"/api/curation/works/{work['id']}/unpublish").status_code == 200
    assert anon_client.get(f"/public/works/{work['slug']}").status_code == 404
    assert anon_client.get(f"/public/pages/{s['page']['id']}").status_code == 404
    assert client.get(f"/api/curation/works/{work['id']}").json()["status"] == "draft"
    # The projection page row is preserved (preview resolves it regardless of status).
    assert client.get(f"/api/curation/pages/{s['page']['id']}/preview").status_code == 200


# === gated publication lifecycle ===========================================


def test_publish_requires_approval_and_admin(
    client: TestClient, editor_client: TestClient
) -> None:
    work = _published_work(client)
    _structure(client, work["id"])

    # Cannot publish without an approved request.
    assert client.post(f"/api/curation/works/{work['id']}/publish").status_code == 409

    approval = client.post(f"/api/curation/works/{work['id']}/request-approval").json()
    assert approval["status"] == "pending"
    # A non-admin cannot approve.
    assert editor_client.post(
        f"/api/curation/approvals/{approval['id']}/approve", json={}
    ).status_code == 403

    client.post(f"/api/curation/approvals/{approval['id']}/approve", json={})
    assert client.post(f"/api/curation/works/{work['id']}/publish").status_code == 200


def test_validation_blocks_publication(client: TestClient) -> None:
    # No author credit, no pages → blocking errors.
    work = _published_work(client, author_credit=None)
    validation = client.get(f"/api/curation/works/{work['id']}/validate").json()
    assert validation["ok"] is False
    assert validation["errors"] >= 1
    codes = {i["code"] for i in validation["issues"]}
    assert "missing_author_credit" in codes

    approval = client.post(f"/api/curation/works/{work['id']}/request-approval").json()
    # Approval is refused while blocking errors remain.
    assert client.post(
        f"/api/curation/approvals/{approval['id']}/approve", json={}
    ).status_code == 400
    assert client.post(f"/api/curation/works/{work['id']}/publish").status_code == 409


def test_publication_history_preserved(client: TestClient) -> None:
    work = _published_work(client)
    _structure(client, work["id"])
    _approve_and_publish(client, work["id"])
    client.post(f"/api/curation/works/{work['id']}/unpublish")

    events = client.get(f"/api/curation/works/{work['id']}/events").json()
    actions = [e["action"] for e in events["items"]]
    assert "published" in actions
    assert "unpublished" in actions
    assert "created" in actions
    # The paginated history reports its total alongside the page of items.
    assert events["total"] == len(events["items"])
    # Filtering by action narrows the history.
    only_pub = client.get(
        f"/api/curation/works/{work['id']}/events?action=published"
    ).json()
    assert only_pub["total"] >= 1
    assert {e["action"] for e in only_pub["items"]} == {"published"}
    approvals = client.get(f"/api/curation/works/{work['id']}/approvals").json()
    assert approvals["items"][0]["status"] == "approved"


# === controlled hand-off ===================================================


def test_handoff_requires_explicit_public_derivative_and_never_exposes_private(
    client: TestClient, anon_client: TestClient, session: Session
) -> None:
    from app.models import (
        Asset,
        AssetVersion,
        LicenceRecord,
        LicenceReviewState,
        ProvenanceRecord,
    )

    work = _published_work(client)
    s = _structure(client, work["id"])
    gn_page_id = _gn_page(session, _work(client)["id"])

    # A private asset version with a private storage key (never public). Give it
    # cleared provenance + licence so the work still validates for publication.
    asset = Asset(title="Page master", asset_type="page_art")
    session.add(asset)
    session.flush()
    version = AssetVersion(
        asset_id=asset.id, version_number=1, storage_key="assets/secret/master.tiff"
    )
    session.add(version)
    session.flush()
    session.add(ProvenanceRecord(asset_version_id=version.id))
    session.add(LicenceRecord(asset_id=asset.id, review_state=LicenceReviewState.APPROVED))
    session.commit()

    media = _media(client)  # the explicit public derivative

    # Missing/unknown derivative → refused (explicit selection required).
    bad = client.post(
        "/api/curation/handoff/page",
        json={"gn_page_id": gn_page_id, "public_media_asset_id": "nope",
              "chapter_id": s["chapter"]["id"]},
    )
    assert bad.status_code == 404

    handed = client.post(
        "/api/curation/handoff/page",
        json={
            "gn_page_id": gn_page_id, "public_media_asset_id": media["id"],
            "chapter_id": s["chapter"]["id"], "import_panels": True,
            "source_asset_version_id": version.id,
        },
    )
    assert handed.status_code == 201, handed.text
    page = handed.json()
    # The public page uses the PUBLIC derivative path, never the private key.
    assert page["image_path"] == media["file_path"]
    assert "secret" not in page["image_path"]

    # Panels were carried with normalised coordinates.
    panels = client.get(f"/api/curation/pages/{page['id']}/panels").json()
    assert len(panels) == 1
    assert panels[0]["x"] == 0.1 and panels[0]["width"] == 0.8

    # Publish, then confirm the private storage key appears nowhere in /public.
    _approve_and_publish(client, work["id"])
    public_page = anon_client.get(f"/public/pages/{page['id']}")
    assert public_page.status_code == 200
    assert "assets/secret/master.tiff" not in public_page.text
    assert len(public_page.json()["panels"]) == 1


def test_handoff_marks_private_source_and_survives_unpublish(
    client: TestClient, session: Session
) -> None:
    from app.models import GraphicNovelPage

    work = _published_work(client)
    s = _structure(client, work["id"])
    gn_page_id = _gn_page(session, _work(client)["id"])
    media = _media(client, "/public/derivatives/p2.webp")

    client.post(
        "/api/curation/handoff/page",
        json={"gn_page_id": gn_page_id, "public_media_asset_id": media["id"],
              "chapter_id": s["chapter"]["id"]},
    )
    _approve_and_publish(client, work["id"])
    client.post(f"/api/curation/works/{work['id']}/unpublish")

    # The private GraphicNovelPage is untouched and still linked.
    session.expire_all()
    gn_page = session.get(GraphicNovelPage, gn_page_id)
    assert gn_page is not None
    assert gn_page.curation_status.value == "handed_off"
    assert gn_page.published_page_id is not None


# === licence / provenance validation =======================================


def test_publication_validates_licence_and_provenance(
    client: TestClient, session: Session
) -> None:
    from app.models import (
        Asset,
        AssetVersion,
        LicenceRecord,
        LicenceReviewState,
        ProvenanceRecord,
        PublishedPage,
    )

    work = _published_work(client)
    s = _structure(client, work["id"])

    asset = Asset(title="Asset", asset_type="page_art")
    session.add(asset)
    session.flush()
    version = AssetVersion(asset_id=asset.id, version_number=1, storage_key="a/v1")
    session.add(version)
    session.commit()

    # Point the page at the asset version, with no provenance/licence yet.
    page = session.get(PublishedPage, s["page"]["id"])
    page.source_asset_version_id = version.id
    session.add(page)
    session.commit()

    v = client.get(f"/api/curation/works/{work['id']}/validate").json()
    codes = {i["code"] for i in v["issues"]}
    assert "missing_provenance" in codes
    assert "missing_licence" in codes
    assert v["ok"] is False

    # Add provenance + an approved licence → those errors clear.
    session.add(ProvenanceRecord(asset_version_id=version.id))
    session.add(LicenceRecord(asset_id=asset.id, review_state=LicenceReviewState.APPROVED))
    session.commit()
    v2 = client.get(f"/api/curation/works/{work['id']}/validate").json()
    codes2 = {i["code"] for i in v2["issues"]}
    assert "missing_provenance" not in codes2
    assert "missing_licence" not in codes2
    assert v2["ok"] is True


# === preview (exact public representation, admin-only) ======================


def test_preview_shows_public_representation_while_public_404s(
    client: TestClient, anon_client: TestClient
) -> None:
    work = _published_work(client)  # DRAFT
    _structure(client, work["id"])

    preview = client.get(f"/api/curation/works/{work['id']}/preview")
    assert preview.status_code == 200
    body = preview.json()
    assert body["slug"] == work["slug"]
    assert len(body["volumes"]) == 1  # exact public detail shape
    # source_work_id is never in the public projection shape.
    assert "source_work_id" not in body

    # The same work is still invisible publicly.
    assert anon_client.get(f"/public/works/{work['slug']}").status_code == 404
    # Preview is private.
    assert anon_client.get(f"/api/curation/works/{work['id']}/preview").status_code == 401


# === auth ==================================================================


def test_curation_requires_auth(anon_client: TestClient) -> None:
    assert anon_client.get("/api/curation/works").status_code == 401
    assert anon_client.post("/api/curation/works", json={"title": "x"}).status_code == 401
    assert anon_client.post(
        "/api/curation/handoff/page",
        json={"gn_page_id": "a", "public_media_asset_id": "b", "chapter_id": "c"},
    ).status_code == 401
