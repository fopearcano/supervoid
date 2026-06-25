"""End-to-end integration tests for the principal SUPERVOID studio workflows.

Unlike the per-domain suites, these drive several bounded contexts in sequence
through the public HTTP API and assert that the *seams* between them hold: the
command centre aggregates a freshly built work, an adaptation hands off from
publishing into pictures, and the private curation pipeline projects to the
public reader while unpublished material stays invisible.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tmp_storage(monkeypatch, tmp_path):
    """Point the cached storage backend at a temp dir for upload steps."""
    from app.services import storage as storage_mod

    monkeypatch.setattr(storage_mod, "_storage", storage_mod.LocalFileStorage(tmp_path))
    return tmp_path


def _author(client: TestClient, name: str = "E2E Maker") -> str:
    return client.post("/api/authors", json={"full_name": name}).json()["id"]


def _upload(client: TestClient, asset_id: str, content: bytes) -> dict:
    r = client.post(
        f"/api/assets/{asset_id}/versions/upload",
        files={"file": ("art.png", io.BytesIO(content), "image/png")},
    )
    assert r.status_code == 201, r.text
    return r.json()


# --- 1. narrative -> production -> assets -> agents -> command centre -------


def test_e2e_one_person_studio_pipeline(client: TestClient, admin_user, tmp_storage) -> None:
    author = _author(client)
    world = client.post("/api/story-worlds", json={"name": "E2E World"}).json()
    work = client.post("/api/works", json={
        "title": "E2E Graphic Novel", "author_id": author,
        "story_world_id": world["id"], "primary_division": "publishing",
        "primary_medium": "graphic_novel",
    }).json()
    ms = client.post("/api/manuscripts", json={
        "title": "E2E Script", "author_id": author, "work_id": work["id"],
    }).json()

    # Production: a task and a human approval request.
    task = client.post(
        "/api/production-tasks", json={"title": "Ink page 1", "work_id": work["id"]}
    ).json()
    approval = client.post(
        f"/api/production-tasks/{task['id']}/approvals",
        json={"approver_id": admin_user.id, "title": "Approve inks"},
    )
    assert approval.status_code == 201, approval.text
    assert approval.json()["status"] == "pending"

    # Assets: a versioned asset (real storage) with provenance and a licence.
    asset = client.post("/api/assets", json={
        "title": "E2E Cover", "asset_type": "cover", "work_id": work["id"],
    }).json()
    version = _upload(client, asset["id"], b"cover-bytes")
    prov = client.put(
        f"/api/assets/{asset['id']}/versions/{version['id']}/provenance",
        json={"kind": "human_created", "provider": "hand"},
    )
    assert prov.status_code == 200, prov.text
    licence = client.post(
        f"/api/assets/{asset['id']}/licences",
        json={"licence_type": "proprietary", "rights_holder": "Studio"},
    )
    assert licence.status_code == 201, licence.text

    # Agents: a read-only analysis (manuscript) and a propose-only run (work).
    assert client.post(
        "/api/agents/manuscript_consistency/run",
        json={"target_type": "manuscript", "target_id": ms["id"]},
    ).status_code == 201
    assert client.post(
        "/api/agents/work_metadata_advisor/run",
        json={"target_type": "work", "target_id": work["id"]},
    ).status_code == 201

    # The command centre aggregates the whole chain.
    overview = client.get("/api/command-centre/overview").json()
    assert overview["story_worlds"] >= 1 and overview["works_total"] >= 1

    cmd = client.get(f"/api/command-centre/works/{work['id']}/command").json()
    assert any(n["id"] == ms["id"] for n in cmd["narrative"])
    assert cmd["production"]["total"] >= 1
    assert cmd["assets"]["total"] >= 1
    assert cmd["agent_history"]  # the work run is recorded against the work

    inbox = client.get("/api/command-centre/agent-inbox").json()
    assert inbox["open_findings"] >= 1 or inbox["pending_proposals"]


# --- 2. adaptation hand-off: publishing -> pictures ------------------------


def test_e2e_adaptation_handoff_publishing_to_pictures(client: TestClient) -> None:
    author = _author(client)
    work = client.post("/api/works", json={
        "title": "Adaptable Work", "author_id": author, "primary_division": "publishing",
    }).json()

    dossier = client.post("/api/adaptation-dossiers", json={
        "source_work_id": work["id"], "target_medium": "film",
        "target_division": "pictures", "logline": "A tide myth, on screen.",
        "status": "in_development",  # advanced enough to spin up a screen project
    })
    assert dossier.status_code == 201, dossier.text
    dossier_id = dossier.json()["id"]

    # Hand off into the Pictures division as a ScreenProject.
    project = client.post(
        f"/api/screen/projects/from-dossier/{dossier_id}",
        json={"format": "film", "title": "The Drowned Cathedral (Film)"},
    )
    assert project.status_code == 201, project.text
    assert project.json()["source_work_id"] == work["id"]

    # The adaptation shows on the source work's command page and in the overview.
    cmd = client.get(f"/api/command-centre/works/{work['id']}/command").json()
    assert any(a["kind"] == "adaptation" for a in cmd["adaptations"])
    overview = client.get("/api/command-centre/overview").json()
    assert any(m["count"] >= 1 for m in overview["adaptation_dossiers"])


# --- 3. curation hand-off + public/private isolation -----------------------


def test_e2e_curation_publishes_and_isolates(client: TestClient, anon_client: TestClient) -> None:
    # Build a published work through the private curation CMS. An author credit
    # is required to clear publication validation.
    pub = client.post(
        "/api/curation/works",
        json={"title": "Curated GN", "slug": "curated-gn", "author_credit": "A. Maker"},
    ).json()
    vol = client.post(
        f"/api/curation/works/{pub['id']}/volumes",
        json={"title": "V1", "volume_number": 1},
    ).json()
    ch = client.post(
        f"/api/curation/volumes/{vol['id']}/chapters",
        json={"title": "C1", "chapter_number": 1},
    ).json()
    client.post(
        f"/api/curation/chapters/{ch['id']}/pages",
        json={"page_number": 1, "image_path": "/public/demo/p1.svg"},
    )

    # A draft is invisible through the public reader.
    assert anon_client.get("/public/works").json() == []
    assert anon_client.get(f"/public/works/{pub['slug']}").status_code == 404

    # Approve + publish, then it becomes publicly visible.
    approval = client.post(f"/api/curation/works/{pub['id']}/request-approval").json()
    client.post(f"/api/curation/approvals/{approval['id']}/approve", json={})
    published = client.post(f"/api/curation/works/{pub['id']}/publish")
    assert published.status_code == 200, published.text

    public_list = anon_client.get("/public/works").json()
    assert [w["slug"] for w in public_list] == ["curated-gn"]
    detail = anon_client.get(f"/public/works/{pub['slug']}")
    assert detail.status_code == 200

    # A second, still-draft work stays invisible — isolation holds.
    draft = client.post(
        "/api/curation/works", json={"title": "Secret GN", "slug": "secret-gn"}
    ).json()
    assert draft["status"] == "draft"
    slugs = [w["slug"] for w in anon_client.get("/public/works").json()]
    assert "secret-gn" not in slugs
    # The publication history records the lifecycle (paginated).
    events = client.get(f"/api/curation/works/{pub['id']}/events").json()
    assert events["total"] >= 1
    actions = {e["action"] for e in events["items"]}
    assert "published" in actions
