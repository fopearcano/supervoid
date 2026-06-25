"""The operational, local-first integration hub.

Covers: the adapter registry; secure configuration (env-referenced secrets,
masked status, no raw secret retrieval); the approval boundary every external
mutation must pass through (read-only/dry-run run now, mutations await approval,
external actions need an admin); the n8n / ComfyUI / GitHub / file-exchange
adapters; run history; and preservation of the existing integration endpoints.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select


# --- helpers ---------------------------------------------------------------


def _point(client: TestClient, **over) -> dict:
    payload = {
        "name": "Test point",
        "adapter_key": "comfyui",
        "config": {"base_url": "http://127.0.0.1:8188"},
    }
    payload.update(over)
    r = client.post("/api/integrations/points", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _production_task(session: Session, title: str = "Link target") -> str:
    from app.models import ProductionItem

    task = ProductionItem(title=title)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task.id


def _request_op(client: TestClient, point_id: str, operation: str, payload=None, dry_run=False) -> dict:
    r = client.post(
        f"/api/integrations/points/{point_id}/operations",
        json={"operation": operation, "payload": payload or {}, "dry_run": dry_run},
    )
    assert r.status_code == 201, r.text
    return r.json()


# --- existing endpoints preserved ------------------------------------------


def test_existing_integration_endpoints_preserved(
    anon_client: TestClient, client: TestClient
) -> None:
    assert anon_client.get("/api/integrations").status_code == 200
    assert anon_client.get("/api/integrations/ecosystem").status_code == 200
    assert anon_client.get("/api/integrations/logosforge").status_code == 200
    # A descriptive point with no adapter still works.
    point = _point(client, name="Descriptive", adapter_key=None, config={})
    assert point["adapter_key"] is None
    assert client.get(f"/api/integrations/points/{point['id']}").status_code == 200


# --- adapter registry ------------------------------------------------------


def test_adapter_registry_lists_all_adapters(client: TestClient) -> None:
    adapters = client.get("/api/integrations/adapters").json()
    by_key = {a["key"]: a for a in adapters}
    # The four adapter families, including a file-exchange profile per app.
    assert {"n8n_webhook", "comfyui", "github_project"} <= set(by_key)
    for app in (
        "affinity", "indesign", "clip_studio", "davinci_resolve",
        "blender", "cinema4d", "houdini",
    ):
        assert f"file_exchange.{app}" in by_key

    # Operation metadata drives the approval boundary.
    send = next(o for o in by_key["n8n_webhook"]["operations"] if o["key"] == "send_event")
    assert send["external"] is True and send["requires_approval"] is True
    assert send["admin_gated"] is True
    status_op = next(o for o in by_key["comfyui"]["operations"] if o["key"] == "query_status")
    assert status_op["read_only"] is True


def test_adapters_require_auth(anon_client: TestClient) -> None:
    assert anon_client.get("/api/integrations/adapters").status_code == 401


# --- secure configuration --------------------------------------------------


def test_credential_refs_must_be_env_names_not_secrets(client: TestClient) -> None:
    # A raw secret value (not an env-var name) is rejected.
    bad = client.post(
        "/api/integrations/points",
        json={
            "name": "Bad creds",
            "adapter_key": "github_project",
            "credential_refs": {"token": "ghp_supersecretvalue"},
        },
    )
    assert bad.status_code == 422
    # An ENV VAR NAME is accepted.
    ok = client.post(
        "/api/integrations/points",
        json={
            "name": "Good creds",
            "adapter_key": "github_project",
            "config": {"owner": "supervoid", "repo": "wp"},
            "credential_refs": {"token": "SUPERVOID_GITHUB_TOKEN"},
        },
    )
    assert ok.status_code == 201


def test_read_never_exposes_credential_refs(client: TestClient) -> None:
    point = _point(
        client, adapter_key="github_project",
        config={"owner": "supervoid", "repo": "wp"},
        credential_refs={"token": "SUPERVOID_GITHUB_TOKEN"},
    )
    # The env-var names are not in any read payload.
    assert "credential_refs" not in point
    fetched = client.get(f"/api/integrations/points/{point['id']}").json()
    assert "credential_refs" not in fetched


def test_config_status_masks_and_reports_presence(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    point = _point(
        client, adapter_key="github_project",
        config={"owner": "supervoid", "repo": "wp"},
        credential_refs={"token": "SUPERVOID_GITHUB_TOKEN"},
    )
    # Unset env -> credential reported absent, no value leaked.
    monkeypatch.delenv("SUPERVOID_GITHUB_TOKEN", raising=False)
    cfg = client.get(f"/api/integrations/points/{point['id']}/config").json()
    assert cfg["credentials"] == {"token": False}
    assert cfg["missing_config"] == []  # owner + repo present
    assert "SUPERVOID_GITHUB_TOKEN" not in str(cfg)  # env-var name never returned

    # Set env -> reported present (still a boolean only).
    monkeypatch.setenv("SUPERVOID_GITHUB_TOKEN", "ghp_secret")
    cfg2 = client.get(f"/api/integrations/points/{point['id']}/config").json()
    assert cfg2["credentials"] == {"token": True}
    assert "ghp_secret" not in str(cfg2)


def test_health_reports_not_configured_when_required_config_missing(client: TestClient) -> None:
    point = _point(client, adapter_key="github_project", config={})  # no owner/repo
    health = client.get(f"/api/integrations/points/{point['id']}/health").json()
    assert health["status"] == "not_configured"
    assert "owner" in health["missing_config"]


def test_health_unknown_when_configured_local_first(client: TestClient) -> None:
    point = _point(client)  # comfyui with base_url
    health = client.get(f"/api/integrations/points/{point['id']}/health").json()
    # Local-first: liveness not probed, so status is 'unknown', not 'unreachable'.
    assert health["status"] == "unknown"
    assert health["configured"] is True
    assert health["checked_live"] is False


# --- read-only and dry-run run immediately ---------------------------------


def test_read_only_operation_runs_immediately(client: TestClient) -> None:
    point = _point(client)
    run = _request_op(client, point["id"], "query_status", {"prompt_id": "p1"})
    assert run["status"] == "succeeded"
    assert run["requires_approval"] is False
    # No assumption ComfyUI is running: degrades to an offline result.
    assert run["output"]["reachable"] is False


def test_run_correlation_id_matches_request_id(client: TestClient) -> None:
    """An integration run is traceable back to the HTTP request that asked for
    it: its correlation_id is the inbound X-Request-ID."""
    point = _point(client)
    r = client.post(
        f"/api/integrations/points/{point['id']}/operations",
        json={"operation": "query_status", "payload": {"prompt_id": "p1"}, "dry_run": False},
        headers={"X-Request-ID": "trace-integration-1"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["correlation_id"] == "trace-integration-1"


def test_dry_run_external_operation_has_no_side_effect(client: TestClient) -> None:
    point = _point(client, adapter_key="n8n_webhook", config={"webhook_url": "http://x/y"})
    run = _request_op(
        client, point["id"], "send_event",
        {"event_type": "demo", "data": {"a": 1}}, dry_run=True,
    )
    assert run["status"] == "succeeded"
    assert run["dry_run"] is True
    assert run["output"]["would_send"]["url"] == "http://x/y"
    assert "dispatched" not in run["output"]  # nothing was sent


# --- the approval boundary for external mutations --------------------------


def test_external_mutation_requires_admin_approval_then_records(
    client: TestClient, editor_client: TestClient
) -> None:
    point = _point(client, adapter_key="n8n_webhook", config={"webhook_url": "http://x/y"})
    run = _request_op(client, point["id"], "send_event", {"event_type": "e"})
    rid = run["id"]
    assert run["status"] == "pending_approval"  # external -> awaits approval

    # Cannot execute before approval.
    assert client.post(f"/api/integrations/runs/{rid}/execute").status_code == 409

    # A non-admin cannot approve an external (admin-gated) action.
    assert editor_client.post(f"/api/integrations/runs/{rid}/approve").status_code == 403

    approved = client.post(f"/api/integrations/runs/{rid}/approve").json()
    assert approved["status"] == "approved"

    executed = client.post(f"/api/integrations/runs/{rid}/execute").json()
    assert executed["status"] == "succeeded"
    # Local-first: dispatched=False, the event is recorded not sent.
    assert executed["output"]["mode"] == "recorded"
    assert executed["output"]["dispatched"] is False


def test_internal_mutation_is_gated_but_not_admin_only(
    editor_client: TestClient, session: Session
) -> None:
    point = _point(
        editor_client, adapter_key="github_project",
        config={"owner": "supervoid", "repo": "wp"},
    )
    task_id = _production_task(session)
    run = _request_op(
        editor_client, point["id"], "link_commit",
        {"external_ref": "deadbeef", "title": "Fix typo", "target_id": task_id},
    )
    rid = run["id"]
    assert run["status"] == "pending_approval"  # mutating -> needs approval
    # A non-admin CAN approve an internal (non-external) mutation.
    assert editor_client.post(f"/api/integrations/runs/{rid}/approve").json()["status"] == "approved"
    executed = editor_client.post(f"/api/integrations/runs/{rid}/execute").json()
    assert executed["status"] == "succeeded"
    assert executed["output"]["external_kind"] == "commit"

    # The link is now queryable and points at the task.
    links = editor_client.get(f"/api/integrations/links?target_id={task_id}").json()
    assert links["total"] == 1
    assert links["items"][0]["external_ref"] == "deadbeef"


def test_rejected_run_cannot_execute(client: TestClient) -> None:
    point = _point(client, adapter_key="n8n_webhook", config={"webhook_url": "http://x/y"})
    run = _request_op(client, point["id"], "send_event", {"event_type": "e"})
    rid = run["id"]
    rejected = client.post(
        f"/api/integrations/runs/{rid}/reject", json={"reason": "not now"}
    ).json()
    assert rejected["status"] == "rejected"
    assert client.post(f"/api/integrations/runs/{rid}/execute").status_code == 409


def test_link_to_missing_task_fails_on_execute(client: TestClient) -> None:
    point = _point(client, adapter_key="github_project", config={"owner": "o", "repo": "r"})
    run = _request_op(
        client, point["id"], "link_commit",
        {"external_ref": "abc", "target_id": "does-not-exist"},
    )
    client.post(f"/api/integrations/runs/{run['id']}/approve")
    executed = client.post(f"/api/integrations/runs/{run['id']}/execute").json()
    assert executed["status"] == "failed"
    assert "not found" in (executed["error"] or "").lower()


# --- ComfyUI: attach output -> asset + provenance --------------------------


def test_comfyui_attach_output_creates_asset_version_and_provenance(
    client: TestClient, session: Session
) -> None:
    from app.models import AssetVersion, ProvenanceKind, ProvenanceRecord

    point = _point(client)
    run = _request_op(
        client, point["id"], "attach_output_to_asset",
        {
            "new_asset": {"title": "Generated key art", "asset_type": "concept_art"},
            "output": {"filename": "out_0001.png", "mime_type": "image/png"},
            "provenance": {
                "base_model": "sdxl-1.0", "prompt": "a quiet print workshop",
                "seed": 12345, "sampler": "dpmpp_2m",
            },
            "workflow_id": "wf-77",
        },
    )
    assert run["status"] == "pending_approval"
    client.post(f"/api/integrations/runs/{run['id']}/approve")
    executed = client.post(f"/api/integrations/runs/{run['id']}/execute").json()
    assert executed["status"] == "succeeded"
    version_id = executed["output"]["asset_version_id"]

    version = session.get(AssetVersion, version_id)
    assert version is not None
    assert version.storage_key.startswith("placeholder:comfyui/")
    prov = session.exec(
        select(ProvenanceRecord).where(ProvenanceRecord.asset_version_id == version_id)
    ).first()
    assert prov is not None
    assert prov.kind == ProvenanceKind.AI_GENERATED
    assert prov.provider == "comfyui"
    assert prov.base_model == "sdxl-1.0"
    assert prov.generating_workflow == "wf-77"


def test_comfyui_import_workflow_metadata_records_provenance(
    client: TestClient, session: Session
) -> None:
    from app.models import ProvenanceRecord

    point = _point(client)
    # First create an asset version via attach.
    attach = _request_op(
        client, point["id"], "attach_output_to_asset",
        {"new_asset": {"title": "Base"}, "output": {"filename": "a.png"}},
    )
    client.post(f"/api/integrations/runs/{attach['id']}/approve")
    version_id = client.post(
        f"/api/integrations/runs/{attach['id']}/execute"
    ).json()["output"]["asset_version_id"]

    imp = _request_op(
        client, point["id"], "import_workflow_metadata",
        {"asset_version_id": version_id, "provenance": {"base_model": "flux.1"},
         "workflow": {"nodes": []}},
    )
    client.post(f"/api/integrations/runs/{imp['id']}/approve")
    executed = client.post(f"/api/integrations/runs/{imp['id']}/execute").json()
    assert executed["status"] == "succeeded"
    records = session.exec(
        select(ProvenanceRecord).where(ProvenanceRecord.asset_version_id == version_id)
    ).all()
    assert len(records) == 2  # the attach one + the imported one


# --- file-exchange: export package + import deliverable --------------------


def test_file_exchange_export_dry_run_returns_manifest(client: TestClient) -> None:
    point = _point(client, adapter_key="file_exchange.affinity", config={})
    run = _request_op(
        client, point["id"], "export_package",
        {"title": "Cover layout", "items": [{"asset_id": "x", "type": "cover"}]},
        dry_run=True,
    )
    assert run["status"] == "succeeded"
    manifest = run["output"]["manifest"]
    assert manifest["app"] == "affinity"
    assert manifest["schema"].startswith("supervoid.file_exchange/")


def test_file_exchange_export_writes_package(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from app.services import storage as storage_module
    from app.services.storage import LocalFileStorage

    monkeypatch.setattr(storage_module, "_storage", LocalFileStorage(tmp_path))
    point = _point(client, adapter_key="file_exchange.indesign", config={})
    run = _request_op(
        client, point["id"], "export_package",
        {"correlation_id": "demo", "items": [{"asset_id": "x"}]},
    )
    client.post(f"/api/integrations/runs/{run['id']}/approve")
    executed = client.post(f"/api/integrations/runs/{run['id']}/execute").json()
    assert executed["status"] == "succeeded"
    package_key = executed["output"]["package_key"]
    assert (tmp_path / package_key).is_file()


def test_file_exchange_import_creates_asset_with_provenance(
    client: TestClient, session: Session
) -> None:
    from app.models import AssetVersion, ProvenanceKind, ProvenanceRecord

    point = _point(client, adapter_key="file_exchange.clip_studio", config={})
    run = _request_op(
        client, point["id"], "import_package",
        {
            "new_asset": {"title": "Inked page 12", "asset_type": "page_art"},
            "deliverable": {"path": "page-012.clip", "format": "clip"},
        },
    )
    client.post(f"/api/integrations/runs/{run['id']}/approve")
    executed = client.post(f"/api/integrations/runs/{run['id']}/execute").json()
    assert executed["status"] == "succeeded"
    version = session.get(AssetVersion, executed["output"]["asset_version_id"])
    assert version.storage_key.startswith("placeholder:clip_studio/")
    prov = session.exec(
        select(ProvenanceRecord).where(ProvenanceRecord.asset_version_id == version.id)
    ).first()
    assert prov.kind == ProvenanceKind.MIXED
    assert "Clip Studio" in (prov.provider or "")


# --- secrets never persisted in run payloads -------------------------------


def test_secret_like_keys_are_redacted_in_runs(client: TestClient) -> None:
    point = _point(client, adapter_key="n8n_webhook", config={"webhook_url": "http://x/y"})
    run = _request_op(
        client, point["id"], "send_event",
        {"event_type": "e", "data": {"api_key": "sk-leak", "ok": "fine"}},
        dry_run=True,
    )
    # Both the persisted input and output have the secret-like key scrubbed.
    assert run["input"]["data"]["api_key"] == "[redacted]"
    assert run["input"]["data"]["ok"] == "fine"
    assert "sk-leak" not in str(run["output"])


# --- run history & disabled / unbound points -------------------------------


def test_run_history_lists_and_filters(client: TestClient) -> None:
    point = _point(client)
    _request_op(client, point["id"], "query_status", {"prompt_id": "1"})
    _request_op(client, point["id"], "query_status", {"prompt_id": "2"})
    runs = client.get(f"/api/integrations/runs?point_id={point['id']}").json()
    assert runs["total"] >= 2
    succeeded = client.get("/api/integrations/runs?status=succeeded").json()
    assert all(r["status"] == "succeeded" for r in succeeded["items"])


def test_operation_on_disabled_point_is_rejected(client: TestClient) -> None:
    point = _point(client, enabled=False)
    r = client.post(
        f"/api/integrations/points/{point['id']}/operations",
        json={"operation": "query_status", "payload": {}},
    )
    assert r.status_code == 409


def test_operation_on_point_without_adapter_is_rejected(client: TestClient) -> None:
    point = _point(client, adapter_key=None, config={})
    r = client.post(
        f"/api/integrations/points/{point['id']}/operations",
        json={"operation": "query_status", "payload": {}},
    )
    assert r.status_code == 409


def test_unknown_operation_is_404(client: TestClient) -> None:
    point = _point(client)
    r = client.post(
        f"/api/integrations/points/{point['id']}/operations",
        json={"operation": "no_such_op", "payload": {}},
    )
    assert r.status_code == 404


def test_hub_requires_auth(anon_client: TestClient) -> None:
    assert anon_client.get("/api/integrations/runs").status_code == 401
    assert anon_client.post(
        "/api/integrations/points/x/operations",
        json={"operation": "query_status"},
    ).status_code == 401


# --- LOGOSFORGE: local-first bundle import (adapter-only) -------------------


def _lf_point(client: TestClient) -> dict:
    return _point(client, name="LOGOSFORGE", adapter_key="logosforge", config={})


def test_logosforge_adapter_registered_and_local_first(client: TestClient) -> None:
    adapters = {a["key"]: a for a in client.get("/api/integrations/adapters").json()}
    assert "logosforge" in adapters
    ops = {o["key"]: o for o in adapters["logosforge"]["operations"]}
    # import is inbound + mutating (gated, not admin); notes are external (admin-gated).
    assert ops["import_manuscript"]["mutating"] is True
    assert ops["import_manuscript"]["external"] is False
    assert ops["return_editorial_notes"]["external"] is True
    # Local-first health needs no configuration.
    point = _lf_point(client)
    health = client.get(f"/api/integrations/points/{point['id']}/health").json()
    assert health["status"] == "healthy"


def test_logosforge_import_manuscript_dry_run_then_creates(client: TestClient) -> None:
    point = _lf_point(client)
    bundle = {
        "manuscript": {
            "title": "The Drowned Cathedral",
            "synopsis": "A tide myth.",
            "word_count": 42000,
        },
        "author": {"full_name": "Wren Calloway"},
    }
    # Dry-run previews and creates nothing.
    dry = _request_op(client, point["id"], "import_manuscript", bundle, dry_run=True)
    assert dry["status"] == "succeeded"
    assert dry["output"]["would_create"]["manuscript_title"] == "The Drowned Cathedral"
    assert "manuscript_id" not in dry["output"]

    # Real run: mutating -> gated -> approve -> execute.
    run = _request_op(client, point["id"], "import_manuscript", bundle)
    rid = run["id"]
    assert run["status"] == "pending_approval"
    assert client.post(f"/api/integrations/runs/{rid}/approve").json()["status"] == "approved"
    executed = client.post(f"/api/integrations/runs/{rid}/execute").json()
    assert executed["status"] == "succeeded"
    ms_id = executed["output"]["manuscript_id"]
    fetched = client.get(f"/api/manuscripts/{ms_id}").json()
    assert fetched["title"] == "The Drowned Cathedral"
    assert fetched["word_count"] == 42000


def test_logosforge_sync_knowledge_graph_is_idempotent(client: TestClient) -> None:
    point = _lf_point(client)
    bundle = {"knowledge": {
        "entities": [
            {"kind": "character", "name": "Wren"},
            {"kind": "place", "name": "The Cathedral"},
        ],
        "relationships": [
            {"source": "Wren", "target": "The Cathedral", "kind": "inhabits"}
        ],
    }}

    def _run_sync() -> dict:
        run = _request_op(client, point["id"], "sync_knowledge_graph", bundle)
        rid = run["id"]
        client.post(f"/api/integrations/runs/{rid}/approve")
        return client.post(f"/api/integrations/runs/{rid}/execute").json()

    first = _run_sync()
    assert first["status"] == "succeeded"
    assert first["output"]["entities_created"] == 2
    assert first["output"]["relationships_created"] == 1
    # A re-sync de-duplicates entities by slug — nothing new is created.
    second = _run_sync()
    assert second["output"]["entities_created"] == 0


def test_logosforge_return_notes_is_admin_gated_and_recorded(
    client: TestClient, editor_client: TestClient
) -> None:
    point = _lf_point(client)
    run = _request_op(
        client, point["id"], "return_editorial_notes",
        {"manuscript_id": "ms-1", "notes": [{"text": "tighten act II"}]},
    )
    rid = run["id"]
    assert run["status"] == "pending_approval"
    # External -> a non-admin cannot approve.
    assert editor_client.post(f"/api/integrations/runs/{rid}/approve").status_code == 403
    assert client.post(f"/api/integrations/runs/{rid}/approve").json()["status"] == "approved"
    executed = client.post(f"/api/integrations/runs/{rid}/execute").json()
    assert executed["status"] == "succeeded"
    # Recorded, never dispatched (local-first; no live LOGOSFORGE API).
    assert executed["output"]["mode"] == "recorded"
    assert executed["output"]["dispatched"] is False
