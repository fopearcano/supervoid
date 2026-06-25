"""The supervised studio-agent framework: registry, immediate read-only runs,
gated mutation proposals, approval/execution, admin-gated high-risk actions,
snapshot/history preservation, retry-as-new-run, secret redaction, dry-run, and
preservation of the existing manuscript AI layer."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select


def _author(client: TestClient, name: str = "Maker") -> str:
    return client.post("/api/authors", json={"full_name": name}).json()["id"]


def _work(client: TestClient, **over) -> dict:
    payload = {"title": "W", "author_id": _author(client)}
    payload.update(over)
    r = client.post("/api/works", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _manuscript(client: TestClient, **over) -> dict:
    payload = {"title": "MS", "author_id": _author(client)}
    payload.update(over)
    r = client.post("/api/manuscripts", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# --- registry --------------------------------------------------------------


def test_registry_lists_agents_and_tools(client: TestClient) -> None:
    agents = client.get("/api/agents").json()
    keys = {a["key"] for a in agents}
    assert {"manuscript_consistency", "work_metadata_advisor", "publishing_readiness"} <= keys

    tools = client.get("/api/agents/tools").json()
    by_key = {t["key"]: t for t in tools}
    assert by_key["read_entity"]["kind"] == "read_only"
    assert by_key["publish_to_public_reader"]["always_requires_approval"] is True


# --- read-only run executes immediately ------------------------------------


def test_read_only_run_creates_findings_immediately(client: TestClient) -> None:
    ms = _manuscript(client)  # no synopsis -> a finding
    run = client.post(
        "/api/agents/manuscript_consistency/run",
        json={"target_type": "manuscript", "target_id": ms["id"]},
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["status"] == "succeeded"
    assert body["provider"] == "dry_run"  # dry-run preserved
    assert body["proposal_count"] == 0  # read-only never proposes
    assert len(body["findings"]) >= 1
    assert body["input_snapshot"]["id"] == ms["id"]  # snapshot preserved
    assert "checked" in body["result"]


# --- mutation becomes a gated proposal -------------------------------------


def test_propose_only_run_creates_pending_proposal(client: TestClient) -> None:
    work = _work(client)  # no internal_pitch -> advisor proposes one
    run = client.post(
        "/api/agents/work_metadata_advisor/run",
        json={"target_type": "work", "target_id": work["id"]},
    ).json()
    assert len(run["proposals"]) == 1
    proposal = run["proposals"][0]
    assert proposal["status"] == "pending"
    assert proposal["tool_key"] == "update_work_metadata"
    assert proposal["requires_approval"] is True


def test_execution_requires_approval_then_mutates(client: TestClient) -> None:
    work = _work(client)
    run = client.post(
        "/api/agents/work_metadata_advisor/run",
        json={"target_type": "work", "target_id": work["id"]},
    ).json()
    pid = run["proposals"][0]["id"]

    # Cannot execute while pending.
    assert client.post(f"/api/agent-proposals/{pid}/execute").status_code == 409

    approved = client.post(f"/api/agent-proposals/{pid}/approve").json()
    assert approved["status"] == "approved"

    executed = client.post(f"/api/agent-proposals/{pid}/execute").json()
    assert executed["status"] == "executed"
    assert "internal_pitch" in executed["execution_result"]["updated_fields"]

    # The mutation really applied to the Work.
    assert client.get(f"/api/works/{work['id']}").json()["internal_pitch"]


# --- high-risk actions need admin approval and never auto-fire --------------


def test_publishing_proposal_is_admin_gated_and_recorded(
    client: TestClient, editor_client: TestClient, session: Session
) -> None:
    from app.models import PublishedPage

    work = _work(client)
    run = client.post(
        "/api/agents/publishing_readiness/run",
        json={"target_type": "work", "target_id": work["id"]},
    ).json()
    pid = run["proposals"][0]["id"]
    assert run["proposals"][0]["tool_key"] == "publish_to_public_reader"

    before = len(session.exec(select(PublishedPage)).all())

    # A non-admin cannot approve an always-gated action.
    assert editor_client.post(f"/api/agent-proposals/{pid}/approve").status_code == 403

    # Admin approves and executes — but publishing is only *recorded*, never fired.
    client.post(f"/api/agent-proposals/{pid}/approve")
    executed = client.post(f"/api/agent-proposals/{pid}/execute").json()
    assert executed["status"] == "executed"
    assert executed["execution_result"]["mode"] == "recorded"
    assert len(session.exec(select(PublishedPage)).all()) == before  # nothing published


# --- run permissions -------------------------------------------------------


def test_run_permissions_enforced(client: TestClient, editor_client: TestClient) -> None:
    work = _work(client)
    # publishing_readiness requires the 'publish' permission; a global editor
    # without project membership is refused, an admin is allowed.
    assert editor_client.post(
        "/api/agents/publishing_readiness/run",
        json={"target_type": "work", "target_id": work["id"]},
    ).status_code == 403
    assert client.post(
        "/api/agents/publishing_readiness/run",
        json={"target_type": "work", "target_id": work["id"]},
    ).status_code == 201


# --- retry creates a new run -----------------------------------------------


def test_retry_creates_new_run(client: TestClient) -> None:
    ms = _manuscript(client)
    first = client.post(
        "/api/agents/manuscript_consistency/run",
        json={"target_type": "manuscript", "target_id": ms["id"]},
    ).json()
    retried = client.post(f"/api/agent-runs/{first['id']}/retry").json()
    assert retried["id"] != first["id"]
    assert retried["retry_of_id"] == first["id"]

    history = client.get("/api/agent-runs?agent_key=manuscript_consistency").json()
    assert history["total"] >= 2  # original preserved, not overwritten


# --- findings inbox --------------------------------------------------------


def test_findings_inbox_and_resolve(client: TestClient) -> None:
    ms = _manuscript(client)
    client.post(
        "/api/agents/manuscript_consistency/run",
        json={"target_type": "manuscript", "target_id": ms["id"]},
    )
    inbox = client.get(f"/api/agent-findings?resolved=false&target_id={ms['id']}").json()
    assert inbox["total"] >= 1
    fid = inbox["items"][0]["id"]
    resolved = client.post(f"/api/agent-findings/{fid}/resolve").json()
    assert resolved["resolved"] is True


# --- prompt templates (version tracking) -----------------------------------


def test_prompt_template_versioning(client: TestClient) -> None:
    created = client.post(
        "/api/prompt-templates",
        json={"key": "t.summary", "name": "Summary", "body": "v1 body"},
    )
    assert created.status_code == 201
    assert created.json()["current_version"] == 1

    v2 = client.post(
        "/api/prompt-templates/t.summary/versions",
        json={"body": "v2 body", "notes": "revised"},
    ).json()
    assert v2["version"] == 2
    assert client.get("/api/prompt-templates/t.summary").json()["current_version"] == 2
    versions = client.get("/api/prompt-templates/t.summary/versions").json()
    assert [v["version"] for v in versions] == [2, 1]  # append-only history


# --- safety invariants -----------------------------------------------------


def test_redact_strips_secrets() -> None:
    from app.services import agents

    cleaned = agents.redact(
        {"api_key": "sk-secret", "title": "ok", "nested": {"token": "t", "keep": 1}}
    )
    assert cleaned["api_key"] == "[redacted]"
    assert cleaned["nested"]["token"] == "[redacted]"
    assert cleaned["title"] == "ok"
    assert cleaned["nested"]["keep"] == 1


def test_unsupported_entity_type_rejected(client: TestClient) -> None:
    work = _work(client)
    # manuscript_consistency supports only manuscripts.
    assert client.post(
        "/api/agents/manuscript_consistency/run",
        json={"target_type": "work", "target_id": work["id"]},
    ).status_code == 400


def test_existing_ai_layer_preserved(client: TestClient) -> None:
    # The manuscript AI endpoints are untouched.
    assert client.get("/api/ai/providers").status_code == 200


def test_agent_centre_requires_auth(anon_client: TestClient) -> None:
    assert anon_client.get("/api/agents").status_code == 401
    assert anon_client.get("/api/agent-runs").status_code == 401
