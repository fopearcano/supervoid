"""The general production task system: backward compatibility, validated
transitions, dependencies, subtasks, milestones, human approvals (no AI
auto-approval), activity, the query endpoints, and template application."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.security import create_access_token


# --- helpers ---------------------------------------------------------------


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token(user: dict) -> str:
    token, _ = create_access_token(subject=user["id"], role=user["role"])
    return token


def _mk_user(client: TestClient, email: str, role: str = "production_manager") -> dict:
    r = client.post(
        "/api/users",
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "password": "password123",
            "role": role,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


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


def _task(client: TestClient, work_id: str, **over) -> dict:
    payload = {"title": "A task", "work_id": work_id}
    payload.update(over)
    r = client.post("/api/production-tasks", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# --- backward compatibility ------------------------------------------------


def test_legacy_production_items_still_work(client: TestClient) -> None:
    """The original /production-items surface is unchanged."""
    author = _author_id(client)
    ms = client.post(
        "/api/manuscripts", json={"title": "MS", "author_id": author}
    )
    assert ms.status_code == 201, ms.text
    manuscript_id = ms.json()["id"]

    created = client.post(
        "/api/production-items",
        json={"manuscript_id": manuscript_id, "stage": "layout"},
    )
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["status"] == "pending"
    assert item["stage"] == "layout"

    moved = client.patch(
        f"/api/production-items/{item['id']}", json={"status": "in_progress"}
    )
    assert moved.status_code == 200 and moved.json()["status"] == "in_progress"


# --- create / read ---------------------------------------------------------


def test_create_task_defaults_and_creator(client: TestClient, admin_user) -> None:
    work = _work(client)
    task = _task(client, work["id"], title="Write script", track="script")
    assert task["status"] == "todo"
    assert task["task_type"] == "task"
    assert task["priority"] == "medium"
    assert task["creator_id"] == admin_user.id
    assert task["title"] == "Write script"
    assert task["revision_number"] == 0

    # Activity records the creation.
    activity = client.get(f"/api/production-tasks/{task['id']}/activity").json()
    assert any(a["type"] == "created" for a in activity)


def test_create_task_validates_refs(client: TestClient) -> None:
    assert client.post(
        "/api/production-tasks", json={"title": "x", "work_id": "nope"}
    ).status_code == 404


# --- validated transitions -------------------------------------------------


def test_valid_and_invalid_transitions(client: TestClient) -> None:
    work = _work(client)
    task = _task(client, work["id"])

    ok = client.post(
        f"/api/production-tasks/{task['id']}/transition",
        json={"to_status": "in_progress"},
    )
    assert ok.status_code == 200 and ok.json()["status"] == "in_progress"

    # in_progress -> done is legal and sets the completed date.
    done = client.post(
        f"/api/production-tasks/{task['id']}/transition", json={"to_status": "done"}
    )
    assert done.status_code == 200
    assert done.json()["status"] == "done"
    assert done.json()["completed_date"] is not None


def test_illegal_transition_rejected(client: TestClient) -> None:
    work = _work(client)
    task = _task(client, work["id"])  # starts in todo
    # todo -> done is not allowed (must pass through in_progress).
    bad = client.post(
        f"/api/production-tasks/{task['id']}/transition", json={"to_status": "done"}
    )
    assert bad.status_code == 422


def test_status_change_via_patch_is_validated(client: TestClient) -> None:
    work = _work(client)
    task = _task(client, work["id"])
    assert client.patch(
        f"/api/production-tasks/{task['id']}", json={"status": "done"}
    ).status_code == 422
    assert client.patch(
        f"/api/production-tasks/{task['id']}", json={"status": "in_progress"}
    ).json()["status"] == "in_progress"


# --- dependencies ----------------------------------------------------------


def test_dependencies_block_completion(client: TestClient) -> None:
    work = _work(client)
    a = _task(client, work["id"], title="A")
    b = _task(client, work["id"], title="B")

    # A depends on B.
    dep = client.post(
        f"/api/production-tasks/{a['id']}/dependencies",
        json={"depends_on_id": b["id"]},
    )
    assert dep.status_code == 201
    assert dep.json()["depends_on_id"] == b["id"]
    assert dep.json()["satisfied"] is False

    # A can start, but cannot finish while B is open.
    client.post(f"/api/production-tasks/{a['id']}/transition", json={"to_status": "in_progress"})
    blocked = client.post(
        f"/api/production-tasks/{a['id']}/transition", json={"to_status": "done"}
    )
    assert blocked.status_code == 409

    # Finish B, then A may finish.
    client.post(f"/api/production-tasks/{b['id']}/transition", json={"to_status": "in_progress"})
    client.post(f"/api/production-tasks/{b['id']}/transition", json={"to_status": "done"})
    ok = client.post(
        f"/api/production-tasks/{a['id']}/transition", json={"to_status": "done"}
    )
    assert ok.status_code == 200


def test_dependency_self_and_cycle_rejected(client: TestClient) -> None:
    work = _work(client)
    a = _task(client, work["id"], title="A")
    b = _task(client, work["id"], title="B")

    assert client.post(
        f"/api/production-tasks/{a['id']}/dependencies",
        json={"depends_on_id": a["id"]},
    ).status_code == 400

    client.post(
        f"/api/production-tasks/{a['id']}/dependencies", json={"depends_on_id": b["id"]}
    )
    # b depends on a would close a cycle.
    assert client.post(
        f"/api/production-tasks/{b['id']}/dependencies", json={"depends_on_id": a["id"]}
    ).status_code == 409


def test_unmet_dependency_marks_task_blocked(client: TestClient) -> None:
    work = _work(client)
    a = _task(client, work["id"], title="A")
    b = _task(client, work["id"], title="B")
    client.post(
        f"/api/production-tasks/{a['id']}/dependencies", json={"depends_on_id": b["id"]}
    )
    detail = client.get(f"/api/production-tasks/{a['id']}").json()
    assert detail["is_blocked"] is True
    assert detail["blocked_by_dependencies"] is True
    assert b["id"] in detail["unmet_dependency_ids"]

    listed = client.get(f"/api/production-tasks/blocked?work_id={work['id']}").json()
    assert a["id"] in [t["id"] for t in listed]


# --- subtasks --------------------------------------------------------------


def test_subtasks(client: TestClient) -> None:
    work = _work(client)
    parent = _task(client, work["id"], title="Parent")
    child = _task(client, work["id"], title="Child", parent_id=parent["id"])
    assert child["parent_id"] == parent["id"]

    subs = client.get(f"/api/production-tasks/{parent['id']}/subtasks").json()
    assert [s["id"] for s in subs] == [child["id"]]
    assert client.get(f"/api/production-tasks/{parent['id']}").json()["subtask_count"] == 1

    # A task cannot be its own parent.
    assert client.patch(
        f"/api/production-tasks/{parent['id']}", json={"parent_id": parent["id"]}
    ).status_code == 400


# --- milestones ------------------------------------------------------------


def test_milestones_and_linking(client: TestClient) -> None:
    work = _work(client)
    ms = client.post(
        "/api/milestones",
        json={"title": "Art complete", "work_id": work["id"], "target_date": "2030-01-01"},
    )
    assert ms.status_code == 201, ms.text
    milestone = ms.json()

    task = _task(client, work["id"], milestone_id=milestone["id"])
    tasks = client.get(f"/api/milestones/{milestone['id']}/tasks").json()
    assert [t["id"] for t in tasks] == [task["id"]]
    assert client.get(f"/api/milestones/{milestone['id']}").json()["task_count"] == 1


# --- approvals (human-gated, no AI auto-approval) --------------------------


def test_approval_flow_is_human_gated(client: TestClient) -> None:
    work = _work(client)
    task = _task(client, work["id"])
    approver = _mk_user(client, "approver@x.test")
    other = _mk_user(client, "other@x.test")

    req = client.post(
        f"/api/production-tasks/{task['id']}/approvals",
        json={"approver_id": approver["id"], "title": "Approve files"},
    )
    assert req.status_code == 201, req.text
    approval = req.json()
    assert approval["status"] == "pending"

    # The approver sees it in their awaiting-approval queue.
    queue = client.get(
        "/api/production-tasks/awaiting-approval", headers=_auth(_token(approver))
    ).json()
    assert approval["id"] in [a["id"] for a in queue]

    # A non-approver, non-admin cannot decide.
    assert client.post(
        f"/api/approvals/{approval['id']}/decide",
        json={"decision": "approved"},
        headers=_auth(_token(other)),
    ).status_code == 403

    # The assigned approver decides.
    decided = client.post(
        f"/api/approvals/{approval['id']}/decide",
        json={"decision": "approved", "comments": "Looks good"},
        headers=_auth(_token(approver)),
    )
    assert decided.status_code == 200
    body = decided.json()
    assert body["status"] == "approved"
    assert body["decision"] == "approved"
    assert body["decided_at"] is not None

    # Deciding twice is rejected.
    assert client.post(
        f"/api/approvals/{approval['id']}/decide",
        json={"decision": "rejected"},
        headers=_auth(_token(approver)),
    ).status_code == 400


def test_approving_does_not_complete_the_task(client: TestClient) -> None:
    """AI-safety invariant proxy: approving a deliverable must NOT auto-advance
    the task to done/approved — completion stays a separate human transition."""
    work = _work(client)
    task = _task(client, work["id"])
    approver = _mk_user(client, "appr2@x.test")
    approval = client.post(
        f"/api/production-tasks/{task['id']}/approvals",
        json={"approver_id": approver["id"]},
    ).json()
    client.post(
        f"/api/approvals/{approval['id']}/decide",
        json={"decision": "approved"},
        headers=_auth(_token(approver)),
    )
    # Task is untouched by the approval decision.
    assert client.get(f"/api/production-tasks/{task['id']}").json()["status"] == "todo"


def test_no_ai_auto_complete_or_approve_in_service() -> None:
    """The workflow engine marks completion/approval as human-only."""
    from app.models import ProductionItemStatus
    from app.services import production

    assert ProductionItemStatus.DONE in production.HUMAN_ONLY_STATUSES
    assert ProductionItemStatus.APPROVED in production.HUMAN_ONLY_STATUSES


# --- query endpoints -------------------------------------------------------


def test_my_assignments_and_overdue(client: TestClient) -> None:
    work = _work(client)
    me = _mk_user(client, "worker@x.test")
    token = _token(me)
    mine = _task(client, work["id"], title="Mine", assignee_id=me["id"])
    _task(client, work["id"], title="Theirs")
    overdue = _task(
        client, work["id"], title="Late", assignee_id=me["id"], due_date="2000-01-01"
    )

    assigned = client.get(
        "/api/production-tasks/my-assignments", headers=_auth(token)
    ).json()
    assert {mine["id"], overdue["id"]} == {t["id"] for t in assigned["items"]}

    late = client.get("/api/production-tasks/overdue").json()
    assert overdue["id"] in [t["id"] for t in late["items"]]


def test_list_filters(client: TestClient) -> None:
    work = _work(client)
    _task(client, work["id"], title="Art", track="art", priority="high")
    _task(client, work["id"], title="Snd", track="sound")

    assert client.get(f"/api/production-tasks?track=art&work_id={work['id']}").json()["total"] == 1
    assert client.get(f"/api/production-tasks?priority=high&work_id={work['id']}").json()["total"] == 1


# --- templates -------------------------------------------------------------


def test_list_templates(client: TestClient) -> None:
    templates = client.get("/api/production-templates").json()
    keys = {t["key"] for t in templates}
    assert {
        "graphic_novel_volume",
        "book_publication",
        "short_film",
        "feature_film",
        "animated_sequence",
        "promotional_launch",
    } <= keys


def test_apply_template_builds_breakdown(client: TestClient) -> None:
    work = _work(client)
    applied = client.post(
        f"/api/works/{work['id']}/production-template",
        json={"template_key": "graphic_novel_volume"},
    )
    assert applied.status_code == 201, applied.text
    result = applied.json()
    assert len(result["task_ids"]) == 9
    assert len(result["milestone_ids"]) == 3
    assert len(result["dependency_ids"]) >= 1

    # The tasks really landed on the work, wired to milestones.
    tasks = client.get(f"/api/production-tasks?work_id={work['id']}&limit=50").json()
    assert tasks["total"] == 9
    milestones = client.get(f"/api/milestones?work_id={work['id']}").json()
    assert milestones["total"] == 3

    # Unknown template -> 404.
    assert client.post(
        f"/api/works/{work['id']}/production-template",
        json={"template_key": "nope"},
    ).status_code == 404


# --- auth gating -----------------------------------------------------------


def test_task_writes_require_auth(anon_client: TestClient) -> None:
    assert anon_client.post(
        "/api/production-tasks", json={"title": "x", "work_id": "y"}
    ).status_code == 401
    assert anon_client.get("/api/production-tasks/my-assignments").status_code == 401


def test_task_delete_is_admin_only(client: TestClient, editor_client: TestClient) -> None:
    work = _work(client)
    task = _task(client, work["id"])
    assert editor_client.delete(f"/api/production-tasks/{task['id']}").status_code == 403
    assert client.delete(f"/api/production-tasks/{task['id']}").status_code == 204
