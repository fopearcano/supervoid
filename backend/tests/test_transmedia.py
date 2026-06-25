from __future__ import annotations

from fastapi.testclient import TestClient


def _author(client: TestClient, name: str = "A. Maker") -> str:
    r = client.post("/api/authors", json={"full_name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _world(client: TestClient, **over) -> dict:
    payload = {"name": "A World"}
    payload.update(over)
    r = client.post("/api/story-worlds", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _series(client: TestClient, world_id: str, **over) -> dict:
    payload = {"story_world_id": world_id, "title": "Arc"}
    payload.update(over)
    r = client.post("/api/story-series", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _work(client: TestClient, author_id: str, **over) -> dict:
    payload = {"title": "A Work", "author_id": author_id}
    payload.update(over)
    r = client.post("/api/works", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# --- Story worlds ----------------------------------------------------------


def test_story_world_crud_and_slug(client: TestClient) -> None:
    w1 = _world(client, name="The Bound World")
    assert w1["slug"] == "the-bound-world"
    assert w1["status"] == "developing"
    assert w1["default_language"] == "en"

    # Same name -> a distinct, unique slug.
    w2 = _world(client, name="The Bound World")
    assert w2["slug"] != w1["slug"]

    assert client.get("/api/story-worlds").json()["total"] == 2
    assert client.get(f"/api/story-worlds/{w1['id']}").status_code == 200

    patched = client.patch(
        f"/api/story-worlds/{w1['id']}",
        json={"status": "active", "canon_summary": "Canon holds."},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "active"

    assert client.delete(f"/api/story-worlds/{w1['id']}").status_code == 204
    assert client.get(f"/api/story-worlds/{w1['id']}").status_code == 404


def test_story_world_validation(client: TestClient) -> None:
    assert client.post("/api/story-worlds", json={"name": "X", "owner_id": "nope"}).status_code == 404

    parent = _world(client, name="Parent")
    child = _world(client, name="Child", parent_id=parent["id"])
    assert child["parent_id"] == parent["id"]

    assert client.post("/api/story-worlds", json={"name": "Y", "parent_id": "nope"}).status_code == 404
    # A world cannot be its own parent.
    self_parent = client.patch(
        f"/api/story-worlds/{parent['id']}", json={"parent_id": parent["id"]}
    )
    assert self_parent.status_code == 400


def test_story_world_owner_link(client: TestClient) -> None:
    owner = _author(client, "Iris Aldoria")
    world = _world(client, name="Owned World", owner_id=owner)
    assert world["owner_id"] == owner
    assert client.get(f"/api/story-worlds?owner_id={owner}").json()["total"] == 1


# --- Series ----------------------------------------------------------------


def test_story_series_crud_and_filter(client: TestClient) -> None:
    world = _world(client, name="Series World")
    series = _series(client, world["id"], title="Arc One", sequence_order=1)
    assert series["status"] == "planned"
    assert series["story_world_id"] == world["id"]

    assert client.post(
        "/api/story-series", json={"story_world_id": "nope", "title": "X"}
    ).status_code == 404

    assert client.get(f"/api/story-series?story_world_id={world['id']}").json()["total"] == 1

    patched = client.patch(f"/api/story-series/{series['id']}", json={"status": "ongoing"})
    assert patched.json()["status"] == "ongoing"
    assert client.delete(f"/api/story-series/{series['id']}").status_code == 204


# --- Work transmedia placement --------------------------------------------


def test_work_transmedia_placement_and_filters(client: TestClient) -> None:
    author = _author(client)
    world = _world(client, name="Placement World")
    series = _series(client, world["id"])

    gn = _work(
        client, author, title="GN", work_type="graphic_novel",
        story_world_id=world["id"], story_series_id=series["id"], series_order=1,
        primary_division="publishing", primary_medium="graphic_novel",
        canon_status="canon",
    )
    assert gn["story_world_id"] == world["id"]
    assert gn["primary_medium"] == "graphic_novel"
    assert gn["canon_status"] == "canon"

    film = _work(
        client, author, title="Film", work_type="adaptation_candidate",
        story_world_id=world["id"], primary_division="pictures",
        primary_medium="film", canon_status="alternate", source_work_id=gn["id"],
    )
    assert film["source_work_id"] == gn["id"]

    assert client.get(f"/api/works?story_world_id={world['id']}").json()["total"] == 2
    assert client.get(f"/api/works?story_series_id={series['id']}").json()["total"] == 1
    assert client.get("/api/works?primary_division=pictures").json()["total"] == 1
    assert client.get("/api/works?primary_medium=film").json()["total"] == 1
    assert client.get("/api/works?canon_status=alternate").json()["total"] == 1

    bad = client.post(
        "/api/works", json={"title": "bad", "author_id": author, "story_world_id": "nope"}
    )
    assert bad.status_code == 404
    assert bad.json()["detail"] == "StoryWorld not found"


# --- Adaptation dossiers ---------------------------------------------------


def test_adaptation_dossier_crud_and_filters(client: TestClient) -> None:
    author = _author(client)
    src = _work(client, author, title="Source GN", work_type="graphic_novel")
    tgt = _work(client, author, title="Target Film", work_type="adaptation_candidate")

    created = client.post(
        "/api/adaptation-dossiers",
        json={
            "source_work_id": src["id"],
            "target_work_id": tgt["id"],
            "target_medium": "film",
            "target_division": "pictures",
            "status": "in_development",
            "logline": "A quiet correspondence.",
            "rights_clearance": "in_progress",
        },
    )
    assert created.status_code == 201, created.text
    dossier = created.json()
    assert dossier["source_work_title"] == "Source GN"
    assert dossier["target_work_title"] == "Target Film"
    assert dossier["status"] == "in_development"

    assert client.post(
        "/api/adaptation-dossiers", json={"source_work_id": "nope", "target_medium": "film"}
    ).status_code == 404

    assert client.get(f"/api/adaptation-dossiers?source_work_id={src['id']}").json()["total"] == 1
    assert client.get("/api/adaptation-dossiers?status=in_development").json()["total"] == 1
    assert client.get("/api/adaptation-dossiers?target_medium=film").json()["total"] == 1
    assert client.get("/api/adaptation-dossiers?target_division=pictures").json()["total"] == 1
    assert client.get("/api/adaptation-dossiers?rights_clearance=cleared").json()["total"] == 0

    patched = client.patch(
        f"/api/adaptation-dossiers/{dossier['id']}", json={"status": "in_production"}
    )
    assert patched.json()["status"] == "in_production"
    assert client.delete(f"/api/adaptation-dossiers/{dossier['id']}").status_code == 204


# --- Work-level transmedia overview ---------------------------------------


def test_work_transmedia_overview(client: TestClient) -> None:
    author = _author(client)
    world = _world(client, name="Overview World")
    series = _series(client, world["id"])

    src = _work(
        client, author, title="Src", story_world_id=world["id"],
        story_series_id=series["id"],
    )
    derived = _work(client, author, title="Derived", source_work_id=src["id"])
    client.post(
        "/api/adaptation-dossiers",
        json={"source_work_id": src["id"], "target_medium": "film"},
    )

    overview = client.get(f"/api/works/{src['id']}/transmedia")
    assert overview.status_code == 200
    body = overview.json()
    assert body["work"]["id"] == src["id"]
    assert body["story_world"]["id"] == world["id"]
    assert body["story_series"]["id"] == series["id"]
    assert [w["id"] for w in body["derived_works"]] == [derived["id"]]
    assert len(body["adaptation_dossiers"]) == 1


# --- auth gating -----------------------------------------------------------


def test_transmedia_writes_require_auth(anon_client: TestClient) -> None:
    assert anon_client.post("/api/story-worlds", json={"name": "X"}).status_code == 401
    assert anon_client.post("/api/story-series", json={"story_world_id": "x", "title": "y"}).status_code == 401
    assert anon_client.post("/api/adaptation-dossiers", json={"source_work_id": "x", "target_medium": "film"}).status_code == 401


def test_story_world_delete_is_admin_only(
    client: TestClient, editor_client: TestClient
) -> None:
    world = _world(client, name="Protected World")
    assert editor_client.delete(f"/api/story-worlds/{world['id']}").status_code == 403
    assert client.delete(f"/api/story-worlds/{world['id']}").status_code == 204
