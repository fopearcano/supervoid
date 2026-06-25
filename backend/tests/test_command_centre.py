"""The operational command centre — cross-domain roll-ups.

Verifies the seven sections aggregate correctly, that 'my work' is scoped to the
current user, and that the whole surface is private (authenticated).
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session


def _work(client: TestClient, title: str = "W") -> dict:
    author = client.post("/api/authors", json={"full_name": "A"}).json()["id"]
    r = client.post("/api/works", json={"title": title, "author_id": author})
    assert r.status_code == 201, r.text
    return r.json()


# --- auth ------------------------------------------------------------------


def test_command_centre_requires_auth(anon_client: TestClient) -> None:
    for path in (
        "/api/command-centre/overview",
        "/api/command-centre/my-work",
        "/api/command-centre/agent-inbox",
        "/api/command-centre/asset-health",
        "/api/command-centre/business-alerts",
        "/api/command-centre/divisions",
    ):
        assert anon_client.get(path).status_code == 401, path


# --- 1. studio overview ----------------------------------------------------


def test_overview_aggregates(client: TestClient) -> None:
    _work(client, "Overview Work")
    o = client.get("/api/command-centre/overview").json()
    assert o["works_total"] >= 1
    # All studio divisions are represented.
    labels = {d["label"] for d in o["divisions"]}
    assert {"publishing", "pictures", "interactive", "cross_media"} <= labels
    assert "completion_pct" in o["graphic_novel"]
    assert isinstance(o["releases"], list)


# --- 2. my work (scoped to the current user) -------------------------------


def test_my_work_is_user_scoped(client: TestClient, admin_user, session: Session) -> None:
    from app.models import (
        ApprovalRequest,
        ApprovalStatus,
        ProductionItem,
        ProductionItemStatus,
    )

    session.add(ProductionItem(title="Mine", assignee_id=admin_user.id))
    session.add(ProductionItem(
        title="Overdue", assignee_id=admin_user.id,
        due_date=date.today() - timedelta(days=3),
    ))
    session.add(ProductionItem(
        title="Blocked", assignee_id=admin_user.id, status=ProductionItemStatus.BLOCKED,
    ))
    session.add(ApprovalRequest(
        approver_id=admin_user.id, status=ApprovalStatus.PENDING, title="Sign off",
    ))
    session.commit()

    mw = client.get("/api/command-centre/my-work").json()
    assert mw["counts"]["assigned"] >= 1
    assert mw["counts"]["overdue"] >= 1
    assert mw["counts"]["blocked"] >= 1
    assert mw["counts"]["approval_queue"] >= 1
    assert any(t["title"] == "Overdue" and t["days_until"] < 0 for t in mw["overdue"])


def test_my_work_excludes_other_users(editor_client: TestClient, admin_user, session: Session) -> None:
    from app.models import ProductionItem

    session.add(ProductionItem(title="Admins", assignee_id=admin_user.id))
    session.commit()
    # The editor sees none of the admin's assignments.
    mw = editor_client.get("/api/command-centre/my-work").json()
    assert all(t["title"] != "Admins" for t in mw["assigned"])


# --- 3. agent inbox --------------------------------------------------------


def test_agent_inbox_collects_proposals(client: TestClient) -> None:
    work = _work(client, "Agent Work")
    # work_metadata_advisor proposes a (gated) metadata change.
    client.post(
        "/api/agents/work_metadata_advisor/run",
        json={"target_type": "work", "target_id": work["id"]},
    )
    inbox = client.get("/api/command-centre/agent-inbox").json()
    assert len(inbox["pending_proposals"]) >= 1
    assert "findings_by_severity" in inbox


# --- 4 & 5. asset health / business alerts ---------------------------------


def test_asset_health_and_business_alerts_shapes(client: TestClient) -> None:
    health = client.get("/api/command-centre/asset-health").json()
    assert set(health["counts"]) == {
        "missing_files", "incomplete_provenance", "expiring_licences",
        "unapproved_versions", "public_without_credits",
    }
    alerts = client.get("/api/command-centre/business-alerts").json()
    assert set(alerts["counts"]) == {
        "rights_expiries", "contract_deadlines", "distribution_readiness",
        "contact_follow_ups", "upcoming_releases",
    }


def test_business_alerts_surface_rights_expiry(client: TestClient) -> None:
    work = _work(client, "Rights Work")
    client.post("/api/rights", json={
        "work_id": work["id"],
        "expiration_date": (date.today() + timedelta(days=10)).isoformat(),
    })
    alerts = client.get("/api/command-centre/business-alerts").json()
    assert alerts["counts"]["rights_expiries"] >= 1
    assert any(a["work_id"] == work["id"] for a in alerts["rights_expiries"])


# --- 6. division views -----------------------------------------------------


def test_division_views(client: TestClient) -> None:
    _work(client, "Pub Work")
    divisions = client.get("/api/command-centre/divisions").json()
    by_div = {d["division"]: d for d in divisions}
    assert {"publishing", "pictures", "interactive", "cross_media"} <= set(by_div)
    assert by_div["publishing"]["works_count"] >= 1


# --- 7. work command page --------------------------------------------------


def test_work_command_aggregates(client: TestClient) -> None:
    work = _work(client, "Command Work")
    cmd = client.get(f"/api/command-centre/works/{work['id']}/command").json()
    assert cmd["title"] == "Command Work"
    assert set(cmd["production"]) >= {"total", "open", "blocked", "overdue"}
    assert set(cmd["assets"]) >= {"total", "unapproved", "incomplete_provenance"}
    assert "profiles" in cmd["rights"]


def test_work_command_unknown_404(client: TestClient) -> None:
    assert client.get("/api/command-centre/works/nope/command").status_code == 404
