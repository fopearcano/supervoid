"""The central Asset Library: CRUD + search, versioning with checksum dedupe,
promotion/rollback, provenance completeness, licence-expiry warnings, private
preview/download, and isolation from the public reader."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tmp_storage(monkeypatch, tmp_path):
    """Point the cached storage backend at a temp dir for upload tests."""
    from app.services import storage as storage_mod

    monkeypatch.setattr(
        storage_mod, "_storage", storage_mod.LocalFileStorage(tmp_path)
    )
    return tmp_path


def _author_id(client: TestClient, name: str = "Maker") -> str:
    r = client.post("/api/authors", json={"full_name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _work(client: TestClient, **over) -> dict:
    payload = {"title": "W", "author_id": _author_id(client)}
    payload.update(over)
    r = client.post("/api/works", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _asset(client: TestClient, **over) -> dict:
    payload = {"title": "Cover art", "asset_type": "cover"}
    payload.update(over)
    r = client.post("/api/assets", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _upload(client: TestClient, asset_id: str, content: bytes, **data) -> tuple[int, dict]:
    r = client.post(
        f"/api/assets/{asset_id}/versions/upload",
        data={k: str(v) for k, v in data.items()},
        files={"file": ("art.png", io.BytesIO(content), "image/png")},
    )
    return r.status_code, (r.json() if r.content else {})


# --- CRUD + search ---------------------------------------------------------


def test_asset_crud_and_owner_default(client: TestClient, admin_user) -> None:
    work = _work(client)
    asset = _asset(
        client, title="The Cover", work_id=work["id"], tags=["cover", "noir"]
    )
    assert asset["owner_id"] == admin_user.id  # defaults to creator
    assert asset["visibility"] == "private"
    assert asset["version_count"] == 0

    got = client.get(f"/api/assets/{asset['id']}")
    assert got.status_code == 200 and got.json()["title"] == "The Cover"

    patched = client.patch(
        f"/api/assets/{asset['id']}", json={"visibility": "internal"}
    )
    assert patched.json()["visibility"] == "internal"


def test_asset_search_and_filters(client: TestClient) -> None:
    work = _work(client)
    _asset(client, title="Brass Press", asset_type="cover", work_id=work["id"], tags=["a"])
    _asset(client, title="Night Bindery", asset_type="illustration", tags=["b"])

    assert client.get("/api/assets?q=brass").json()["total"] == 1
    assert client.get("/api/assets?asset_type=illustration").json()["total"] == 1
    assert client.get(f"/api/assets?work_id={work['id']}").json()["total"] == 1
    tagged = client.get("/api/assets?tag=a").json()
    assert [a["title"] for a in tagged["items"]] == ["Brass Press"]


# --- versions, checksum dedupe, promotion/rollback -------------------------


def test_upload_version_and_checksum_dedupe(
    client: TestClient, tmp_storage
) -> None:
    asset = _asset(client)
    code, v1 = _upload(client, asset["id"], b"first-bytes")
    assert code == 201, v1
    assert v1["version_number"] == 1
    assert v1["checksum"]
    assert v1["is_current"] is True  # first version becomes current
    assert v1["is_placeholder"] is False

    # Identical bytes -> 409 duplicate.
    dup_code, _ = _upload(client, asset["id"], b"first-bytes")
    assert dup_code == 409

    # Different bytes -> a new version.
    code2, v2 = _upload(client, asset["id"], b"second-bytes")
    assert code2 == 201 and v2["version_number"] == 2
    assert v2["is_current"] is False  # not auto-promoted

    # Cross-asset duplicate discovery by checksum.
    found = client.get(f"/api/assets/versions/by-checksum/{v1['checksum']}").json()
    assert v1["id"] in [m["id"] for m in found["matches"]]


def test_promote_and_rollback(client: TestClient, tmp_storage) -> None:
    asset = _asset(client)
    _, v1 = _upload(client, asset["id"], b"aaa")
    _, v2 = _upload(client, asset["id"], b"bbb")

    promoted = client.post(
        f"/api/assets/{asset['id']}/versions/{v2['id']}/promote"
    ).json()
    assert promoted["current_version_id"] == v2["id"]
    # v1 is now superseded by v2.
    v1_after = next(v for v in promoted["versions"] if v["id"] == v1["id"])
    assert v1_after["superseded_by_id"] == v2["id"]

    rolled = client.post(
        f"/api/assets/{asset['id']}/versions/{v1['id']}/rollback"
    ).json()
    assert rolled["current_version_id"] == v1["id"]

    # Rolling back to a later/equal version is rejected.
    bad = client.post(f"/api/assets/{asset['id']}/versions/{v2['id']}/rollback")
    assert bad.status_code == 400


def test_version_approval_is_explicit(client: TestClient, tmp_storage) -> None:
    asset = _asset(client)
    _, v1 = _upload(client, asset["id"], b"xyz")
    assert v1["approval_status"] == "draft"
    approved = client.post(
        f"/api/assets/{asset['id']}/versions/{v1['id']}/approve",
        json={"approval_status": "approved"},
    ).json()
    assert approved["approval_status"] == "approved"


def test_placeholder_version_download_410(client: TestClient) -> None:
    asset = _asset(client)
    r = client.post(
        f"/api/assets/{asset['id']}/versions",
        json={"mime_type": "image/png", "width": 100, "height": 100},
    )
    assert r.status_code == 201
    version = r.json()
    assert version["is_placeholder"] is True
    gone = client.get(
        f"/api/assets/{asset['id']}/versions/{version['id']}/download"
    )
    assert gone.status_code == 410


def test_download_and_preview(client: TestClient, tmp_storage) -> None:
    asset = _asset(client)
    payload = b"PNGDATA"
    _, v1 = _upload(client, asset["id"], payload)

    dl = client.get(f"/api/assets/{asset['id']}/versions/{v1['id']}/download")
    assert dl.status_code == 200 and dl.content == payload
    assert "attachment" in dl.headers.get("content-disposition", "")

    pv = client.get(f"/api/assets/{asset['id']}/versions/{v1['id']}/preview")
    assert pv.status_code == 200 and pv.content == payload
    assert "inline" in pv.headers.get("content-disposition", "")


# --- provenance ------------------------------------------------------------


def test_provenance_completeness(client: TestClient, admin_user) -> None:
    asset = _asset(client)
    version = client.post(
        f"/api/assets/{asset['id']}/versions", json={"mime_type": "image/png"}
    ).json()
    base = f"/api/assets/{asset['id']}/versions/{version['id']}"

    # AI-generated provenance with nothing filled in -> incomplete.
    client.put(base + "/provenance", json={"kind": "ai_generated"})
    report = client.get(base + "/provenance/completeness").json()
    assert report["complete"] is False
    assert "prompt" in report["missing"]
    assert "responsible_user_id" in report["missing"]

    # Fill the required fields -> complete.
    client.put(
        base + "/provenance",
        json={
            "kind": "ai_generated",
            "provider": "local",
            "base_model": "SUPERVOID-Diffusion",
            "prompt": "a quiet print workshop",
            "generation_date": "2026-06-01T00:00:00",
            "responsible_user_id": admin_user.id,
        },
    )
    report2 = client.get(base + "/provenance/completeness").json()
    assert report2["complete"] is True
    fetched = client.get(base + "/provenance").json()
    assert fetched["base_model"] == "SUPERVOID-Diffusion"


# --- licences + expiry warnings -------------------------------------------


def test_licence_warnings(client: TestClient) -> None:
    from datetime import date, timedelta

    asset = _asset(client)
    soon = (date.today() + timedelta(days=10)).isoformat()
    expired = (date.today() - timedelta(days=2)).isoformat()
    client.post(
        f"/api/assets/{asset['id']}/licences",
        json={"licence_type": "stock", "expiration_date": soon, "review_state": "approved"},
    )
    client.post(
        f"/api/assets/{asset['id']}/licences",
        json={"licence_type": "stock", "expiration_date": expired, "review_state": "approved"},
    )

    warnings = client.get("/api/assets/licence-warnings?within_days=30").json()
    statuses = {w["status"] for w in warnings if w["asset_id"] == asset["id"]}
    assert "expiring_soon" in statuses
    assert "expired" in statuses


# --- links -----------------------------------------------------------------


def test_asset_links(client: TestClient) -> None:
    work = _work(client)
    asset = _asset(client)
    link = client.post(
        f"/api/assets/{asset['id']}/links",
        json={"target_type": "work", "target_id": work["id"], "role": "cover"},
    )
    assert link.status_code == 201
    listed = client.get(f"/api/assets/{asset['id']}/links").json()
    assert listed[0]["id"] == link.json()["id"]
    assert listed[0]["target_id"] == work["id"]
    assert client.delete(
        f"/api/assets/{asset['id']}/links/{listed[0]['id']}"
    ).status_code == 204


# --- auth, admin, and public-reader isolation ------------------------------


def test_asset_library_is_private(anon_client: TestClient) -> None:
    # Every asset route requires authentication.
    assert anon_client.get("/api/assets").status_code == 401
    assert anon_client.get("/api/assets/anything").status_code == 401
    assert anon_client.post("/api/assets", json={"title": "x"}).status_code == 401


def test_delete_asset_is_admin_only(
    client: TestClient, editor_client: TestClient
) -> None:
    asset = _asset(client)
    assert editor_client.delete(f"/api/assets/{asset['id']}").status_code == 403
    assert client.delete(f"/api/assets/{asset['id']}").status_code == 204


def test_assets_never_exposed_via_public_reader(
    client: TestClient, anon_client: TestClient
) -> None:
    asset = _asset(client, title="Secret Cover", visibility="public_candidate")
    # The public reader has no asset surface, and an asset id is not a public
    # media id — even a "public_candidate" asset stays private.
    assert anon_client.get(f"/public/media/{asset['id']}").status_code == 404
    assert anon_client.get("/public/assets").status_code == 404
    # Public works listing never carries asset records.
    works = anon_client.get("/public/works")
    assert works.status_code == 200
    assert "Secret Cover" not in works.text
