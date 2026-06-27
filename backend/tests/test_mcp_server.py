"""The SUPERVOID MCP server (Prompt 10): transport, auth, governance.

Proves: unauthenticated health; the internal service credential is required;
user-context must be signed; tools/list carries governance annotations; read
tools return only authorised records; write-like tools create gated proposals
(never direct mutations); approval tools verify the mapped user's approval scope
(and admin gate for always-gated actions).
"""
from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.models import (
    AgentActionProposal,
    Author,
    ProductionItem,
    ProjectMembership,
    ProposalStatus,
    User,
    UserRole,
    Work,
)
from app.models.enums import MembershipStatus, ProjectRole
from app.services.mcp.auth import sign_user_context

TOKEN = "test-mcp-service-token"


@pytest.fixture(autouse=True)
def _configure_mcp(monkeypatch):
    monkeypatch.setattr("app.config.settings.mcp_service_token", TOKEN)
    monkeypatch.setattr("app.config.settings.mcp_enabled", True)


def _user(session: Session, email: str, role: UserRole) -> User:
    from app.auth.security import hash_password
    from app.services import identity as identity_svc

    u = User(email=email, full_name=email.split("@")[0], role=role,
             hashed_password=hash_password("pw"))
    session.add(u)
    session.commit()
    session.refresh(u)
    # MCP now requires an ACTIVE identity link (Prompt 15). Link every test user.
    identity_svc.link_user(session, supervoid_user_id=u.id, librechat_email=email, verify=True)
    session.commit()
    return u


def _work(session: Session) -> Work:
    a = Author(full_name="A")
    session.add(a)
    session.commit()
    session.refresh(a)
    w = Work(title="W", author_id=a.id)
    session.add(w)
    session.commit()
    session.refresh(w)
    return w


def _member(session, user, work, role: ProjectRole) -> None:
    session.add(ProjectMembership(user_id=user.id, work_id=work.id, role=role,
                                  status=MembershipStatus.ACTIVE))
    session.commit()


def _headers(*, email, token=TOKEN, user_id="lc-1", role="USER", request_id="req-1",
             sign_email=None):
    # sign_email lets a test sign a DIFFERENT email than it sends (tamper case).
    sig = sign_user_context(token, user_id=user_id, email=(sign_email or email),
                            role=role, request_id=request_id)
    return {
        "X-SUPERVOID-Service-Token": token,
        "X-SUPERVOID-User-Id": user_id,
        "X-SUPERVOID-User-Email": email,
        "X-SUPERVOID-User-Role": role,
        "X-SUPERVOID-Request-Id": request_id,
        "X-SUPERVOID-User-Sig": sig,
    }


def _rpc(client, headers, method, params=None, id=1):
    body = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers=headers)


def _call(client, headers, name, arguments=None, id=2):
    return _rpc(client, headers, "tools/call",
                {"name": name, "arguments": arguments or {}}, id=id)


# --- health (unauthenticated) ----------------------------------------------
def test_mcp_health_unauthenticated(anon_client):
    r = anon_client.get("/mcp/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["tool_count"] >= 30
    assert body["server"] == "supervoid"


# --- service credential required -------------------------------------------
def test_requires_service_credential(anon_client, session):
    _user(session, "admin@s.test", UserRole.ADMIN)
    # no headers at all
    r = anon_client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert r.status_code == 401
    # wrong token
    h = _headers(email="admin@s.test", token="wrong-token")
    h["X-SUPERVOID-Service-Token"] = "wrong-token"
    r = _rpc(anon_client, h, "initialize")
    assert r.status_code == 401


def test_user_context_must_be_signed(anon_client, session):
    _user(session, "admin@s.test", UserRole.ADMIN)
    # valid token, but the signature was made over a DIFFERENT email (tamper)
    h = _headers(email="admin@s.test", sign_email="someone-else@s.test")
    r = _rpc(anon_client, h, "tools/list")
    assert r.status_code == 401


def test_unknown_user_rejected(anon_client, session):
    # correctly signed, valid token, but no SUPERVOID user with that email
    h = _headers(email="ghost@nowhere.test")
    r = _rpc(anon_client, h, "tools/list")
    assert r.status_code == 401


# --- initialize + tools/list (annotations) ---------------------------------
def test_initialize_and_tools_list(anon_client, session):
    _user(session, "admin@s.test", UserRole.ADMIN)
    h = _headers(email="admin@s.test")
    init = _rpc(anon_client, h, "initialize",
                {"protocolVersion": "2025-06-18", "capabilities": {}}).json()
    assert init["result"]["serverInfo"]["name"] == "supervoid"
    assert "governance" in init["result"]["instructions"].lower() or \
           "governed" in init["result"]["instructions"].lower()

    listing = _rpc(anon_client, h, "tools/list").json()["result"]["tools"]
    by_name = {t["name"]: t for t in listing}
    assert {"get_studio_state", "propose_task", "approve_proposal", "search_supervoid"} <= set(by_name)
    # every tool carries a concise schema + governance annotation
    for t in listing:
        assert "inputSchema" in t
        ann = t["annotations"]["supervoid"]
        assert ann["kind"] in ("read-only", "proposal-only", "destructive", "external", "approval")
    assert by_name["get_studio_state"]["annotations"]["supervoid"]["kind"] == "read-only"
    assert by_name["propose_task"]["annotations"]["supervoid"]["kind"] == "proposal-only"
    assert by_name["propose_task"]["annotations"]["supervoid"]["requiresApproval"] is True
    assert by_name["approve_proposal"]["annotations"]["supervoid"]["kind"] == "approval"


# --- read tools: only authorised records -----------------------------------
def test_read_tool_permission_enforced(anon_client, session):
    _user(session, "admin@s.test", UserRole.ADMIN)
    editor = _user(session, "ed@s.test", UserRole.EDITOR)
    work = _work(session)

    # admin may read studio state
    r = _call(anon_client, _headers(email="admin@s.test"), "get_studio_state").json()
    assert r["result"]["isError"] is False

    # a non-admin without studio scope cannot
    r = _call(anon_client, _headers(email="ed@s.test"), "get_studio_state").json()
    assert r["result"]["isError"] is True
    assert "scope" in r["result"]["content"][0]["text"].lower()

    # project state: editor (no membership) is refused; admin allowed
    r = _call(anon_client, _headers(email="ed@s.test"),
              "get_project_state", {"work_id": work.id}).json()
    assert r["result"]["isError"] is True
    r = _call(anon_client, _headers(email="admin@s.test"),
              "get_project_state", {"work_id": work.id}).json()
    assert r["result"]["isError"] is False


# --- write-like tools create proposals, never mutations ---------------------
def test_propose_task_creates_gated_proposal_not_mutation(anon_client, session):
    _user(session, "admin@s.test", UserRole.ADMIN)
    work = _work(session)
    before = len(session.exec(select(ProductionItem)).all())

    r = _call(anon_client, _headers(email="admin@s.test"), "propose_task",
              {"work_id": work.id, "title": "Storyboard ch.1"}).json()
    assert r["result"]["isError"] is False
    out = r["result"]["structuredContent"]
    assert out["status"] == "pending" and out["requires_approval"] is True

    # a gated proposal exists; NO production task was created
    props = session.exec(select(AgentActionProposal)).all()
    assert len(props) == 1 and props[0].status == ProposalStatus.PENDING
    assert props[0].tool_key == "create_production_task"
    assert len(session.exec(select(ProductionItem)).all()) == before


def test_propose_task_requires_permission(anon_client, session):
    _user(session, "ed@s.test", UserRole.EDITOR)
    work = _work(session)
    r = _call(anon_client, _headers(email="ed@s.test"), "propose_task",
              {"work_id": work.id, "title": "X"}).json()
    assert r["result"]["isError"] is True
    assert session.exec(select(AgentActionProposal)).first() is None  # nothing created


# --- approval tools verify approval scope ----------------------------------
def test_approval_requires_scope_and_admin_gate(anon_client, session):
    _user(session, "admin@s.test", UserRole.ADMIN)
    editor = _user(session, "ed@s.test", UserRole.EDITOR)
    work = _work(session)

    # admin proposes a normal task
    pid = _call(anon_client, _headers(email="admin@s.test"), "propose_task",
                {"work_id": work.id, "title": "T"}).json()["result"]["structuredContent"]["proposal_id"]

    # editor WITHOUT approval scope is refused
    r = _call(anon_client, _headers(email="ed@s.test"), "approve_proposal",
              {"proposal_id": pid}).json()
    assert r["result"]["isError"] is True

    # grant the editor an OWNER membership (which carries APPROVE) -> allowed
    _member(session, editor, work, ProjectRole.OWNER)
    r = _call(anon_client, _headers(email="ed@s.test"), "approve_proposal",
              {"proposal_id": pid}).json()
    assert r["result"]["isError"] is False
    assert r["result"]["structuredContent"]["status"] == "approved"


def test_always_gated_proposal_needs_admin(anon_client, session):
    _user(session, "admin@s.test", UserRole.ADMIN)
    owner = _user(session, "owner@s.test", UserRole.EDITOR)
    work = _work(session)
    _member(session, owner, work, ProjectRole.OWNER)  # has APPROVE + publish scope

    # admin proposes a publication (publish_to_public_reader is always-gated)
    pid = _call(anon_client, _headers(email="admin@s.test"), "propose_publication",
                {"work_id": work.id}).json()["result"]["structuredContent"]["proposal_id"]

    # even an OWNER (non-admin) cannot approve an always-gated action
    r = _call(anon_client, _headers(email="owner@s.test"), "approve_proposal",
              {"proposal_id": pid}).json()
    assert r["result"]["isError"] is True
    assert "admin" in r["result"]["content"][0]["text"].lower()

    # admin can
    r = _call(anon_client, _headers(email="admin@s.test"), "approve_proposal",
              {"proposal_id": pid}).json()
    assert r["result"]["structuredContent"]["status"] == "approved"


# --- list tools are permission-filtered ------------------------------------
def test_list_action_proposals_filtered_to_authorised(anon_client, session):
    _user(session, "admin@s.test", UserRole.ADMIN)
    outsider = _user(session, "out@s.test", UserRole.EDITOR)
    work = _work(session)
    _call(anon_client, _headers(email="admin@s.test"), "propose_task",
          {"work_id": work.id, "title": "T"})

    # the outsider (no membership) sees none of the work's proposals
    r = _call(anon_client, _headers(email="out@s.test"), "list_action_proposals").json()
    assert r["result"]["structuredContent"]["proposals"] == []
    # admin sees it
    r = _call(anon_client, _headers(email="admin@s.test"), "list_action_proposals").json()
    assert len(r["result"]["structuredContent"]["proposals"]) == 1


# --- unknown tool + notification -------------------------------------------
def test_unknown_tool_is_error(anon_client, session):
    _user(session, "admin@s.test", UserRole.ADMIN)
    r = _call(anon_client, _headers(email="admin@s.test"), "make_coffee").json()
    assert r["result"]["isError"] is True


def test_initialized_notification_no_body(anon_client, session):
    _user(session, "admin@s.test", UserRole.ADMIN)
    # a notification (no id) gets a 202 with no JSON-RPC response
    r = anon_client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                         headers=_headers(email="admin@s.test"))
    assert r.status_code == 202


# --- happy-path smoke across every handler (catches field-name bugs) --------
def test_all_handlers_execute_without_internal_error(anon_client, session):
    """Run every tool with valid input as admin and assert none returns the
    generic 'Tool execution failed' (an unexpected exception). not_found /
    permission isError results are fine — we only fail on internal crashes."""
    from app.models import (
        Asset, AssetVersion, KnowledgeEntity, Manuscript, ProductionItem, Rights,
        StoryWorld,
    )
    from app.models.enums import AssetType, EntityKind

    admin = _user(session, "admin@s.test", UserRole.ADMIN)
    sw = StoryWorld(name="World", slug="world-x")
    session.add(sw); session.commit(); session.refresh(sw)
    a = Author(full_name="A"); session.add(a); session.commit(); session.refresh(a)
    work = Work(title="W", author_id=a.id, story_world_id=sw.id)
    session.add(work); session.commit(); session.refresh(work)
    ms = Manuscript(title="MS", author_id=a.id, work_id=work.id)
    session.add(ms); session.commit(); session.refresh(ms)
    char = KnowledgeEntity(kind=EntityKind.CHARACTER, name="Hero", slug="hero-x")
    place = KnowledgeEntity(kind=EntityKind.PLACE, name="City", slug="city-x")
    session.add(char); session.add(place); session.commit()
    asset = Asset(title="Cover", asset_type=AssetType.IMAGE, work_id=work.id, owner_id=admin.id)
    session.add(asset); session.commit(); session.refresh(asset)
    av = AssetVersion(asset_id=asset.id, version_number=1, storage_key="k/1")
    session.add(av); session.commit(); session.refresh(av)
    asset.current_version_id = av.id
    session.add(asset)
    session.add(ProductionItem(title="Task", work_id=work.id, assignee_id=admin.id))
    session.add(Rights(work_id=work.id))
    session.commit()

    h = _headers(email="admin@s.test")
    calls = [
        ("get_studio_state", {}),
        ("get_project_state", {"work_id": work.id}),
        ("get_project_delta", {"work_id": work.id}),
        ("list_my_projects", {}),
        ("select_active_project", {"work_id": work.id}),
        ("search_supervoid", {"q": "W"}),
        ("get_entity_context", {"entity": "hero-x"}),
        ("get_my_assignments", {}),
        ("get_blocked_tasks", {"work_id": work.id}),
        ("get_pending_approvals", {}),
        ("inspect_production_progress", {"work_id": work.id}),
        ("propose_task", {"work_id": work.id, "title": "T2"}),
        ("get_story_world", {"story_world_id": sw.id}),
        ("get_work_canon", {"work_id": work.id}),
        ("get_character_context", {"character": "hero-x"}),
        ("get_location_context", {"location": "city-x"}),
        ("get_recent_decisions", {"work_id": work.id}),
        ("propose_decision", {"work_id": work.id, "subject": "S", "decision": "D"}),
        ("propose_canon_change", {"work_id": work.id, "summary": "C"}),
        ("search_assets", {"q": "Cover"}),
        ("inspect_asset_version", {"asset_id": asset.id}),
        ("inspect_provenance", {"asset_id": asset.id, "version_id": av.id}),
        ("inspect_licence", {"asset_id": asset.id}),
        ("propose_asset_link", {"asset_id": asset.id, "target_type": "character", "target_id": char.id}),
        ("inspect_publication_readiness", {"work_id": work.id}),
        ("inspect_rights", {"work_id": work.id}),
        ("prepare_distribution_checklist", {"work_id": work.id}),
        ("propose_publication", {"work_id": work.id}),
        ("propose_rights_action", {"work_id": work.id, "action": "review"}),
        ("run_supervoid_agent", {"agent_key": "manuscript_consistency",
                                 "target_type": "manuscript", "target_id": ms.id}),
        ("list_agent_findings", {}),
        ("list_action_proposals", {}),
    ]
    failures = []
    for i, (name, args) in enumerate(calls):
        body = _call(anon_client, h, name, args, id=100 + i).json()
        result = body.get("result", {})
        text = (result.get("content") or [{}])[0].get("text", "")
        if text == "Tool execution failed.":
            failures.append(name)
    assert not failures, f"handlers raised internal errors: {failures}"
