"""The detailed graphic-novel production hierarchy: CRUD + ordering, reorder,
duplication, validation, status roll-up + percentages, readiness, comparison,
knowledge-entity links (no duplication) and the curation hand-off (which never
writes the public reader)."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select


# --- setup helpers ---------------------------------------------------------


def _production(client: TestClient) -> str:
    author = client.post("/api/authors", json={"full_name": "Maker"}).json()["id"]
    work = client.post(
        "/api/works", json={"title": "GN", "author_id": author, "work_type": "graphic_novel"}
    ).json()
    prod = client.post("/api/graphic-novel-productions", json={"work_id": work["id"]})
    assert prod.status_code == 201, prod.text
    return prod.json()["id"]


def _scaffold(client: TestClient) -> dict:
    pid = _production(client)
    vol = client.post(f"/api/graphic-novel-productions/{pid}/volumes", json={}).json()
    chap = client.post(f"/api/gn-volumes/{vol['id']}/chapters", json={}).json()
    seq = client.post(f"/api/gn-chapters/{chap['id']}/sequences", json={}).json()
    return {"production": pid, "volume": vol["id"], "chapter": chap["id"], "sequence": seq["id"]}


def _page(client: TestClient, sequence_id: str, **over) -> dict:
    payload = {"page_number": 1}
    payload.update(over)
    r = client.post(f"/api/gn-sequences/{sequence_id}/pages", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _panel(client: TestClient, page_id: str, **over) -> dict:
    payload = {"panel_number": 1, "x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5}
    payload.update(over)
    r = client.post(f"/api/gn-pages/{page_id}/panels", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _entity(session: Session, name: str, kind: str = "character") -> str:
    from app.models import EntityKind, KnowledgeEntity
    from app.services.knowledge import slugify

    ent = KnowledgeEntity(name=name, slug=slugify(name), kind=EntityKind(kind))
    session.add(ent)
    session.commit()
    session.refresh(ent)
    return ent.id


def _asset_with_versions(session: Session, n: int = 2) -> tuple[str, list[str]]:
    from app.models import Asset, AssetType, AssetVersion

    asset = Asset(title="Art", asset_type=AssetType.PAGE_ART)
    session.add(asset)
    session.commit()
    session.refresh(asset)
    vids = []
    for i in range(1, n + 1):
        v = AssetVersion(
            asset_id=asset.id, version_number=i,
            storage_key=f"placeholder:{asset.id}-{i}", mime_type="image/png",
        )
        session.add(v)
        session.commit()
        session.refresh(v)
        vids.append(v.id)
    return asset.id, vids


# --- CRUD, tree, ordering --------------------------------------------------


def test_build_hierarchy_and_tree(client: TestClient) -> None:
    ids = _scaffold(client)
    page = _page(client, ids["sequence"])
    _panel(client, page["id"], panel_number=1)
    _panel(client, page["id"], panel_number=2)

    tree = client.get(
        f"/api/graphic-novel-productions/{ids['production']}/tree"
    ).json()
    assert len(tree) == 1  # one volume
    assert tree[0]["kind"] == "volume"
    assert tree[0]["children"][0]["children"][0]["children"][0]["kind"] == "page"

    detail = client.get(f"/api/gn-pages/{page['id']}").json()
    assert detail["panel_count"] == 2
    assert len(detail["panels"]) == 2


def test_reorder_pages(client: TestClient) -> None:
    ids = _scaffold(client)
    p1 = _page(client, ids["sequence"], page_number=1)
    p2 = _page(client, ids["sequence"], page_number=2)

    reordered = client.post(
        f"/api/gn-sequences/{ids['sequence']}/pages/reorder",
        json={"ordered_ids": [p2["id"], p1["id"]]},
    ).json()
    assert [p["id"] for p in reordered] == [p2["id"], p1["id"]]
    assert reordered[0]["position"] == 0


# --- validation ------------------------------------------------------------


def test_panel_bounds_validation(client: TestClient) -> None:
    ids = _scaffold(client)
    page = _page(client, ids["sequence"])
    _panel(client, page["id"], x=0.8, y=0.1, width=0.5, height=0.2)  # x+w > 1

    issues = client.get(f"/api/gn-pages/{page['id']}/validate").json()
    assert any("beyond page bounds" in i["message"] for i in issues)


def test_spread_validation(client: TestClient) -> None:
    ids = _scaffold(client)
    # A page with a side but no spread membership is flagged.
    _page(client, ids["sequence"], page_number=1, page_side="left")
    issues = client.get(
        f"/api/graphic-novel-productions/{ids['production']}/validate"
    ).json()
    assert any("no spread membership" in i["message"] for i in issues)

    # A proper spread (one left + one right) raises no spread issue.
    _page(client, ids["sequence"], page_number=2, page_side="left", spread_id="s1")
    _page(client, ids["sequence"], page_number=3, page_side="right", spread_id="s1")
    issues2 = client.get(
        f"/api/graphic-novel-productions/{ids['production']}/validate"
    ).json()
    assert not any(i["level"] == "spread" and i["target_id"] == "s1" for i in issues2)


# --- duplication -----------------------------------------------------------


def test_duplicate_page_and_panel(client: TestClient, session: Session) -> None:
    ids = _scaffold(client)
    page = _page(client, ids["sequence"])
    panel = _panel(client, page["id"])
    entity_id = _entity(session, "Hero")
    client.post(
        f"/api/gn-panels/{panel['id']}/elements",
        json={"element_type": "character", "entity_id": entity_id},
    )

    # Duplicate the panel within the page.
    dup_panel = client.post(f"/api/gn-panels/{panel['id']}/duplicate").json()
    assert dup_panel["panel_number"] == 2
    assert len(dup_panel["elements"]) == 1

    # Duplicate the whole page (clones panels + their elements).
    dup_page = client.post(f"/api/gn-pages/{page['id']}/duplicate").json()
    assert dup_page["page_number"] == 2
    assert dup_page["panel_count"] == 2  # both panels copied
    assert dup_page["panels"][0]["elements"]  # elements copied too


# --- roll-up + progress ----------------------------------------------------


def test_rollup_and_progress(client: TestClient) -> None:
    ids = _scaffold(client)
    page = _page(
        client, ids["sequence"],
        lettering_status="complete", colour_status="complete", final_status="complete",
    )
    _panel(client, page["id"], panel_number=1)

    progress = client.get(
        f"/api/graphic-novel-productions/{ids['production']}/progress"
    ).json()
    assert progress["pages_total"] == 1
    assert progress["final_complete"] == 1
    assert progress["overall_pct"] == 100.0

    # The summary production reflects the rolled-up streams.
    recalced = client.post(
        f"/api/graphic-novel-productions/{ids['production']}/recalculate"
    )
    assert recalced.status_code == 200
    summary = client.get(
        f"/api/graphic-novel-productions/{ids['production']}"
    ).json()
    assert summary["lettering_status"] == "complete"
    assert summary["coloring_status"] == "complete"
    assert summary["final_files_status"] == "complete"


# --- readiness -------------------------------------------------------------


def test_readiness(client: TestClient, session: Session) -> None:
    ids = _scaffold(client)
    page = _page(client, ids["sequence"])

    not_ready = client.get(
        f"/api/graphic-novel-productions/{ids['production']}/readiness"
    ).json()
    assert not_ready["print_ready"] is False
    assert not_ready["digital_ready"] is False

    asset_id, _ = _asset_with_versions(session, n=1)
    client.patch(
        f"/api/gn-pages/{page['id']}",
        json={
            "final_status": "complete", "colour_status": "complete",
            "master_asset_id": asset_id,
            "print_width_mm": 170, "print_height_mm": 240,
            "bleed_mm": 3, "safe_area_mm": 5,
        },
    )
    ready = client.get(
        f"/api/graphic-novel-productions/{ids['production']}/readiness"
    ).json()
    assert ready["print_ready"] is True
    assert ready["digital_ready"] is True


# --- comparison ------------------------------------------------------------


def test_storyboard_final_comparison(client: TestClient, session: Session) -> None:
    ids = _scaffold(client)
    page = _page(client, ids["sequence"])
    panel = _panel(client, page["id"])
    _asset, vids = _asset_with_versions(session, n=2)
    client.patch(
        f"/api/gn-panels/{panel['id']}",
        json={"storyboard_asset_version_id": vids[0], "final_asset_version_id": vids[1]},
    )

    rows = client.get(f"/api/gn-pages/{page['id']}/comparison").json()
    assert len(rows) == 1
    assert rows[0]["storyboard"]["id"] == vids[0]
    assert rows[0]["final"]["id"] == vids[1]


# --- entity links (no duplication) -----------------------------------------


def test_entity_links_reference_knowledge_graph(
    client: TestClient, session: Session
) -> None:
    from app.models import KnowledgeEntity

    ids = _scaffold(client)
    page = _page(client, ids["sequence"])
    panel = _panel(client, page["id"])
    entity_id = _entity(session, "Anselm")

    # Page-level link.
    link = client.post(
        f"/api/gn-pages/{page['id']}/entities",
        json={"entity_id": entity_id, "role": "lead"},
    ).json()
    assert link["entity_name"] == "Anselm"

    # Panel element referencing the same entity (no duplication).
    el = client.post(
        f"/api/gn-panels/{panel['id']}/elements",
        json={"element_type": "character", "entity_id": entity_id},
    ).json()
    assert el["entity_name"] == "Anselm"

    # Removing the link must not delete the knowledge entity.
    assert client.delete(
        f"/api/gn-pages/{page['id']}/entities/{link['id']}"
    ).status_code == 204
    assert session.get(KnowledgeEntity, entity_id) is not None

    # Unknown entity -> 404.
    assert client.post(
        f"/api/gn-pages/{page['id']}/entities", json={"entity_id": "nope"}
    ).status_code == 404


# --- curation hand-off (no public writes) ----------------------------------


def test_curation_handoff_never_publishes(
    client: TestClient, session: Session, anon_client: TestClient
) -> None:
    from app.models import PublishedPage

    ids = _scaffold(client)
    page = _page(client, ids["sequence"])
    asset_id, _ = _asset_with_versions(session, n=1)

    before = len(session.exec(select(PublishedPage)).all())

    # Not eligible yet (no final art / master asset).
    plan = client.get(
        f"/api/graphic-novel-productions/{ids['production']}/curation-handoff"
    ).json()
    assert plan["eligible"] == []
    assert any(p["page_id"] == page["id"] for p in plan["ineligible"])

    # Make it eligible, then hand off with commit.
    client.patch(
        f"/api/gn-pages/{page['id']}",
        json={"final_status": "complete", "master_asset_id": asset_id},
    )
    committed = client.get(
        f"/api/graphic-novel-productions/{ids['production']}/curation-handoff?commit=true"
    ).json()
    assert committed["committed"] is True
    assert any(p["page_id"] == page["id"] for p in committed["eligible"])

    # The page is marked ready — but NOTHING was written to the public reader.
    page_after = client.get(f"/api/gn-pages/{page['id']}").json()
    assert page_after["curation_status"] == "ready_for_curation"
    assert page_after["published_page_id"] is None
    assert len(session.exec(select(PublishedPage)).all()) == before


# --- auth ------------------------------------------------------------------


def test_hierarchy_writes_require_auth(anon_client: TestClient) -> None:
    assert anon_client.post(
        "/api/graphic-novel-productions/x/volumes", json={}
    ).status_code == 401
    assert anon_client.post("/api/gn-pages/x/panels", json={}).status_code == 401
