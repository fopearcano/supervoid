"""SUPERVOID Pictures: dossier promotion, project creation from an approved
dossier (rejecting unapproved), the scene/shot hierarchy, panel↔shot mapping,
carried references (entities/rights/provenance), shot list & breakdown, the
JSON/Markdown adaptation-package export, and isolation from the public reader.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session


# --- helpers ---------------------------------------------------------------


def _work(client: TestClient, **over) -> dict:
    author = client.post("/api/authors", json={"full_name": "Maker"}).json()["id"]
    payload = {"title": "Source", "author_id": author, "work_type": "graphic_novel"}
    payload.update(over)
    r = client.post("/api/works", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _promote(client: TestClient, work_id: str, **over) -> dict:
    payload = {"source_work_id": work_id, "target_medium": "film", "status": "optioned"}
    payload.update(over)
    r = client.post("/api/screen/dossiers/promote", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _project(client: TestClient, dossier_id: str, fmt: str = "film") -> dict:
    r = client.post(
        f"/api/screen/projects/from-dossier/{dossier_id}", json={"format": fmt}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _scene(client: TestClient, project_id: str) -> dict:
    unit = client.get(f"/api/screen/projects/{project_id}/units").json()[0]
    seq = client.post(f"/api/screen/units/{unit['id']}/sequences", json={}).json()
    r = client.post(
        f"/api/screen/sequences/{seq['id']}/scenes",
        json={"scene_number": 1, "heading": "INT. ROOM — DAY", "location": "Room",
              "environment": "int", "time_of_day": "day", "estimated_duration_seconds": 60},
    )
    assert r.status_code == 201, r.text
    return r.json()


# --- promotion + project creation ------------------------------------------


def test_promote_creates_pictures_dossier(client: TestClient) -> None:
    work = _work(client)
    dossier = _promote(client, work["id"])
    assert dossier["target_division"] == "pictures"
    assert dossier["source_work_id"] == work["id"]


def test_project_requires_approved_dossier(client: TestClient) -> None:
    work = _work(client)
    # A merely-proposed dossier cannot yield a project.
    proposed = _promote(client, work["id"], status="proposed")
    rejected = client.post(
        f"/api/screen/projects/from-dossier/{proposed['id']}", json={"format": "film"}
    )
    assert rejected.status_code == 409

    approved = _promote(client, work["id"], status="in_development")
    project = _project(client, approved["id"])
    assert project["format"] == "film"
    assert project["status"] == "development"
    # The project seeds an initial unit.
    units = client.get(f"/api/screen/projects/{project['id']}/units").json()
    assert len(units) == 1
    assert units[0]["unit_type"] == "reel"


def test_series_project_seeds_an_episode(client: TestClient) -> None:
    work = _work(client)
    dossier = _promote(client, work["id"], target_medium="series")
    project = _project(client, dossier["id"], fmt="series")
    units = client.get(f"/api/screen/projects/{project['id']}/units").json()
    assert units[0]["unit_type"] == "episode"


# --- scene + shot hierarchy ------------------------------------------------


def test_scene_and_shot_crud(client: TestClient) -> None:
    work = _work(client)
    project = _project(client, _promote(client, work["id"])["id"])
    scene = _scene(client, project["id"])
    assert scene["heading"] == "INT. ROOM — DAY"

    shot = client.post(
        f"/api/screen/scenes/{scene['id']}/shots",
        json={"shot_number": 1, "framing": "wide", "camera_angle": "low",
              "movement": "dolly", "lens": "35mm", "duration_seconds": 8,
              "dialogue": "Hello.", "vfx": "muzzle flash"},
    )
    assert shot.status_code == 201, shot.text
    assert shot.json()["framing"] == "wide"

    detail = client.get(f"/api/screen/scenes/{scene['id']}").json()
    assert detail["shot_count"] == 1
    assert len(detail["shots"]) == 1


# --- reuse storyboard panels + map panels to shots -------------------------


def _gn_panel(client: TestClient, session: Session, work_id: str) -> str:
    """Build a minimal GN production/panel on the work and return the panel id."""
    prod = client.post(
        "/api/graphic-novel-productions", json={"work_id": work_id}
    ).json()
    vol = client.post(f"/api/graphic-novel-productions/{prod['id']}/volumes", json={}).json()
    chap = client.post(f"/api/gn-volumes/{vol['id']}/chapters", json={}).json()
    seq = client.post(f"/api/gn-chapters/{chap['id']}/sequences", json={}).json()
    page = client.post(f"/api/gn-sequences/{seq['id']}/pages", json={"page_number": 1}).json()
    panel = client.post(f"/api/gn-pages/{page['id']}/panels", json={"panel_number": 1}).json()
    return panel["id"]


def test_storyboard_reuse_and_panel_mapping(client: TestClient, session: Session) -> None:
    work = _work(client)
    panel_id = _gn_panel(client, session, work["id"])
    project = _project(client, _promote(client, work["id"])["id"])
    scene = _scene(client, project["id"])

    # The project surfaces the source work's GN panels as storyboard refs.
    storyboard = client.get(f"/api/screen/projects/{project['id']}/storyboard").json()
    assert panel_id in [r["panel_id"] for r in storyboard]

    shot = client.post(
        f"/api/screen/scenes/{scene['id']}/shots",
        json={"shot_number": 1, "source_storyboard_panel_id": panel_id},
    ).json()
    assert shot["source_storyboard_panel_id"] == panel_id

    # Map an additional panel (many-to-many).
    mapped = client.post(
        f"/api/screen/shots/{shot['id']}/panels", json={"panel_id": panel_id}
    ).json()
    assert panel_id in mapped["mapped_panel_ids"]


# --- carry references (entities / rights / provenance) ---------------------


def test_references_carry_entities_rights_provenance(
    client: TestClient, session: Session
) -> None:
    from app.models import (
        Asset, AssetType, AssetVersion, EntityKind, KnowledgeEntity,
        ProvenanceKind, ProvenanceRecord, Rights,
    )
    from app.services.knowledge import slugify

    work = _work(client)
    # Rights on the source work.
    session.add(Rights(work_id=work["id"], territory="World", holder="SUPERVOID"))
    # A knowledge entity (character) + an asset version with provenance.
    ent = KnowledgeEntity(name="Hero", slug=slugify("Hero"), kind=EntityKind.CHARACTER)
    asset = Asset(title="Plate", asset_type=AssetType.PAGE_ART)
    session.add_all([ent, asset])
    session.commit()
    version = AssetVersion(asset_id=asset.id, version_number=1, storage_key="placeholder:x")
    session.add(version)
    session.commit()
    session.add(ProvenanceRecord(asset_version_id=version.id, kind=ProvenanceKind.AI_ASSISTED, provider="local"))
    session.commit()
    session.refresh(ent)
    session.refresh(version)

    project = _project(client, _promote(client, work["id"])["id"])
    scene = _scene(client, project["id"])
    client.post(f"/api/screen/scenes/{scene['id']}/characters", json={"entity_id": ent.id})
    shot = client.post(f"/api/screen/scenes/{scene['id']}/shots", json={"shot_number": 1}).json()
    client.post(f"/api/screen/shots/{shot['id']}/assets", json={"asset_version_id": version.id})

    refs = client.get(f"/api/screen/projects/{project['id']}/references").json()
    assert "Hero" in [e["name"] for e in refs["entities"]]
    assert len(refs["rights"]) == 1
    assert refs["provenance"][0]["asset_version_id"] == version.id
    assert refs["provenance"][0]["kind"] == "ai_assisted"


# --- shot list / breakdown -------------------------------------------------


def test_shot_list_and_breakdown(client: TestClient) -> None:
    work = _work(client)
    project = _project(client, _promote(client, work["id"])["id"])
    scene = _scene(client, project["id"])
    client.post(f"/api/screen/scenes/{scene['id']}/shots", json={"shot_number": 1, "vfx": "comp"})
    client.post(f"/api/screen/scenes/{scene['id']}/shots", json={"shot_number": 2})

    shot_list = client.get(f"/api/screen/projects/{project['id']}/shot-list").json()
    assert len(shot_list) == 2
    assert shot_list[0]["scene_number"] == 1

    breakdown = client.get(f"/api/screen/projects/{project['id']}/breakdown").json()
    assert breakdown["totals"]["scenes"] == 1
    assert breakdown["totals"]["shots"] == 2
    assert breakdown["totals"]["vfx_shots"] == 1
    assert "Room" in breakdown["totals"]["locations"]


# --- export ----------------------------------------------------------------


def test_export_json_and_markdown(client: TestClient) -> None:
    work = _work(client)
    project = _project(client, _promote(client, work["id"])["id"])
    scene = _scene(client, project["id"])
    client.post(f"/api/screen/scenes/{scene['id']}/shots", json={"shot_number": 1, "dialogue": "Hi."})

    pkg = client.get(f"/api/screen/projects/{project['id']}/export?format=json")
    assert pkg.status_code == 200
    body = pkg.json()
    assert body["project"]["id"] == project["id"]
    assert body["units"][0]["sequences"][0]["scenes"][0]["shots"][0]["shot_number"] == 1
    assert "references" in body

    md = client.get(f"/api/screen/projects/{project['id']}/export?format=markdown")
    assert md.status_code == 200
    assert "text/markdown" in md.headers.get("content-type", "")
    assert "Adaptation package" in md.text
    assert "Shot 1" in md.text


# --- integration descriptor now operational --------------------------------


def test_movies_integration_is_operational(anon_client: TestClient) -> None:
    body = anon_client.get("/api/integrations/supervoid_movies").json()
    assert body["status"] == "available"
    assert "/api/screen" in body["summary"]
    keys = {c["key"] for c in body["capabilities"]}
    assert {"create_screen_project", "export_adaptation_package"} <= keys


# --- auth + public isolation -----------------------------------------------


def test_screen_writes_require_auth(anon_client: TestClient) -> None:
    assert anon_client.post(
        "/api/screen/dossiers/promote", json={"source_work_id": "x"}
    ).status_code == 401
    assert anon_client.post(
        "/api/screen/projects/from-dossier/x", json={}
    ).status_code == 401


def test_screen_not_exposed_via_public_reader(anon_client: TestClient) -> None:
    # The public reader has no screen surface.
    assert anon_client.get("/public/screen").status_code == 404
    assert anon_client.get("/public/projects").status_code == 404
