from __future__ import annotations

from fastapi.testclient import TestClient


# --- Ecosystem integration endpoints (public, read-only) -------------------


def test_list_integrations_declares_siblings(anon_client: TestClient) -> None:
    r = anon_client.get("/api/integrations")
    assert r.status_code == 200
    keys = {i["key"] for i in r.json()}
    assert {"logosforge", "supervoid_movies"} <= keys


def test_ecosystem_map_keeps_systems_distinct(anon_client: TestClient) -> None:
    r = anon_client.get("/api/integrations/ecosystem")
    assert r.status_code == 200
    body = r.json()
    assert body["parent"] == "SUPERVOID ENTANGLED"
    assert body["this_system"] == "SUPERVOID Publishing"

    members = {m["key"]: m for m in body["members"]}
    # The publishing system is the current one; movies and the LOGOSFORGE
    # writing subsystem are separate, non-current members of the ecosystem.
    assert members["supervoid_publishing"]["current"] is True
    assert members["logosforge"]["current"] is False
    assert members["supervoid_movies"]["current"] is False


def test_logosforge_integration_is_a_planned_writing_bridge(
    anon_client: TestClient,
) -> None:
    r = anon_client.get("/api/integrations/logosforge")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "LOGOSFORGE"
    assert body["status"] == "planned"
    assert len(body["capabilities"]) >= 1


def test_unknown_integration_returns_404(anon_client: TestClient) -> None:
    assert anon_client.get("/api/integrations/nope").status_code == 404


# --- Manuscript work types (book vs graphic novel, …) ----------------------


def _author(client: TestClient, name: str = "Test Author") -> str:
    r = client.post("/api/authors", json={"full_name": name})
    assert r.status_code == 201
    return r.json()["id"]


def test_manuscript_defaults_to_book(client: TestClient) -> None:
    author_id = _author(client)
    r = client.post(
        "/api/manuscripts", json={"title": "A Prose Title", "author_id": author_id}
    )
    assert r.status_code == 201
    assert r.json()["work_type"] == "book"


def test_manuscript_accepts_and_filters_by_work_type(client: TestClient) -> None:
    author_id = _author(client, "Graphic Author")
    gn = client.post(
        "/api/manuscripts",
        json={
            "title": "An Illustrated Tale",
            "author_id": author_id,
            "work_type": "graphic_novel",
        },
    )
    assert gn.status_code == 201
    assert gn.json()["work_type"] == "graphic_novel"

    client.post(
        "/api/manuscripts",
        json={"title": "A Plain Book", "author_id": author_id, "work_type": "book"},
    )

    only_gn = client.get("/api/manuscripts?work_type=graphic_novel").json()
    assert only_gn["total"] == 1
    assert only_gn["items"][0]["work_type"] == "graphic_novel"


def test_manuscript_work_type_can_be_patched(client: TestClient) -> None:
    author_id = _author(client, "Mutable Author")
    created = client.post(
        "/api/manuscripts", json={"title": "Shifting Form", "author_id": author_id}
    ).json()
    patched = client.patch(
        f"/api/manuscripts/{created['id']}", json={"work_type": "art_book"}
    )
    assert patched.status_code == 200
    assert patched.json()["work_type"] == "art_book"
