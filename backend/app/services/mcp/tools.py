"""The SUPERVOID MCP tool handlers.

Every tool re-runs authorisation through the policy service against the *mapped
SUPERVOID user* (never the LibreChat-declared role). Read tools return only
authorised records; write-like tools create gated proposals; approval tools
verify the user's approval scope. Handlers return plain JSON-able structures.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session, or_, select

from app.models import (
    AgentActionProposal,
    AgentFinding,
    AgentRiskLevel,
    Asset,
    AssetVersion,
    ApprovalRequest,
    DecisionRecord,
    KnowledgeEntity,
    Manuscript,
    ProductionItem,
    ProposalStatus,
    Rights,
    StoryWorld,
    User,
    UserRole,
    Work,
)
from app.models.base import utcnow
from app.models.enums import (
    AssetVisibility,
    BrainScope,
    DecisionStatus,
    EntityKind,
    FindingSeverity,
    PermissionScope,
    ProductionItemStatus,
)
from app.services import agents as agent_svc
from app.services import assets as asset_svc
from app.services import brain, policy, rights as rights_svc
from app.services.mcp.proposals import create_action_proposal
from app.services.mcp.registry import (
    INT,
    STR,
    MCPToolError,
    ToolKind,
    obj,
    opt_str,
    tool,
)

_CLOSED_TASK = {ProductionItemStatus.DONE, ProductionItemStatus.APPROVED, ProductionItemStatus.CANCELLED}


# --- helpers ---------------------------------------------------------------
def _admin(principal) -> bool:
    return principal.user.role == UserRole.ADMIN


def _can(session, principal, scope, *, work_id=None, story_world_id=None) -> bool:
    return policy.can(session, principal.user, scope, work_id=work_id, story_world_id=story_world_id)


def _require(session, principal, scope, *, work_id=None, story_world_id=None) -> None:
    if not _can(session, principal, scope, work_id=work_id, story_world_id=story_world_id):
        raise MCPToolError(f"Not permitted: {scope.value} required.", code="forbidden")


def _work_of(session: Session, target_type: Optional[str], target_id: Optional[str]):
    """Resolve (work_id, story_world_id) for a target, for permission checks."""
    if not target_id:
        return (None, None)
    if target_type == "work":
        w = session.get(Work, target_id)
        return (target_id, w.story_world_id if w else None)
    if target_type == "story_world":
        return (None, target_id)
    if target_type == "manuscript":
        m = session.get(Manuscript, target_id)
        return ((m.work_id if m else None), None)
    if target_type == "asset":
        a = session.get(Asset, target_id)
        return ((a.work_id if a else None), (a.story_world_id if a else None))
    return (None, None)


def _can_view_target(session, principal, target_type, target_id) -> bool:
    if _admin(principal):
        return True
    work_id, story_world_id = _work_of(session, target_type, target_id)
    if work_id is None and story_world_id is None:
        return True  # unscoped record (e.g. global theme) — authed read allowed
    return _can(session, principal, PermissionScope.VIEW_PROJECT,
                work_id=work_id, story_world_id=story_world_id)


def _state_dict(state) -> dict:
    if state is None:
        return {}
    return {
        "version": state.version, "status": getattr(state.status, "value", None),
        "checksum": state.checksum, "stale": state.stale,
        "compact_summary": state.compact_summary,
        "compiled_at": state.compiled_at.isoformat() if state.compiled_at else None,
    }


# === Context and navigation ================================================
@tool("get_studio_state", title="Get studio state", kind=ToolKind.READ_ONLY,
      description="The compiled studio-wide brain state (admin/studio scope).",
      input_schema=obj({}))
def get_studio_state(session, principal, args):
    if not _admin(principal):
        raise MCPToolError("Studio-wide state requires studio (admin) scope.", code="forbidden")
    return _state_dict(brain.get_studio_state(session))


_PROJECT_ARGS = obj({"work_id": opt_str("Work id"), "story_world_id": opt_str("Story world id")})


def _resolve_scope(args) -> tuple[Optional[str], Optional[str]]:
    work_id = args.get("work_id")
    story_world_id = args.get("story_world_id")
    if not work_id and not story_world_id:
        raise MCPToolError("Provide work_id or story_world_id.", code="invalid_args")
    return work_id, story_world_id


@tool("get_project_state", title="Get project state", kind=ToolKind.READ_ONLY,
      description="The compiled brain state for a Work or StoryWorld.",
      input_schema=_PROJECT_ARGS)
def get_project_state(session, principal, args):
    work_id, story_world_id = _resolve_scope(args)
    _require(session, principal, PermissionScope.VIEW_PROJECT, work_id=work_id, story_world_id=story_world_id)
    state = brain.get_project_state(session, work_id=work_id, story_world_id=story_world_id)
    out = _state_dict(state)
    if state is not None:
        out["canon_digest"] = state.canon_digest
        out["open_questions"] = state.open_questions
        out["priorities"] = state.priorities
    return out


@tool("get_project_delta", title="Get project delta", kind=ToolKind.READ_ONLY,
      description="What changed in a project's compiled state since a version.",
      input_schema=obj({"work_id": opt_str("Work id"), "story_world_id": opt_str("Story world id"),
                        "since_version": INT}))
def get_project_delta(session, principal, args):
    work_id, story_world_id = _resolve_scope(args)
    _require(session, principal, PermissionScope.VIEW_PROJECT, work_id=work_id, story_world_id=story_world_id)
    state = brain.get_project_state(session, work_id=work_id, story_world_id=story_world_id)
    if state is None:
        return {"delta": None, "note": "No compiled state yet."}
    from app.models.enums import BrainStateType
    revs = brain.list_revisions(session, state_type=BrainStateType.PROJECT, state_id=state.id, limit=200)
    since = args.get("since_version")
    cur = next((r for r in revs if r.version == state.version), None)
    prev = (next((r for r in revs if r.version == since), None) if since
            else next((r for r in revs if r.version < state.version), None))
    if not cur or not prev:
        return {"delta": None, "from_version": since, "to_version": state.version,
                "note": "No comparable prior revision."}
    try:
        delta = brain.revision_delta(session, revision_a_id=prev.id, revision_b_id=cur.id)
    except ValueError:
        return {"delta": None}
    return {"from_version": prev.version, "to_version": cur.version,
            "added": delta.get("added"), "removed": delta.get("removed"),
            "changed": delta.get("changed")}


@tool("list_my_projects", title="List my projects", kind=ToolKind.READ_ONLY,
      description="Works and story worlds you have an active membership in.",
      input_schema=obj({}))
def list_my_projects(session, principal, args):
    rows = policy.my_memberships(session, principal.user)
    out = []
    for m in rows:
        if getattr(m.status, "value", m.status) != "active":
            continue
        entry = {"role": getattr(m.role, "value", m.role)}
        if m.work_id:
            w = session.get(Work, m.work_id)
            entry.update({"type": "work", "id": m.work_id, "title": w.title if w else None})
        elif m.story_world_id:
            sw = session.get(StoryWorld, m.story_world_id)
            entry.update({"type": "story_world", "id": m.story_world_id, "name": sw.name if sw else None})
        out.append(entry)
    return {"projects": out}


@tool("select_active_project", title="Select active project", kind=ToolKind.READ_ONLY,
      description="Confirm access to a project and return its current state (advisory).",
      input_schema=_PROJECT_ARGS)
def select_active_project(session, principal, args):
    work_id, story_world_id = _resolve_scope(args)
    _require(session, principal, PermissionScope.VIEW_PROJECT, work_id=work_id, story_world_id=story_world_id)
    state = brain.get_project_state(session, work_id=work_id, story_world_id=story_world_id)
    return {"active": {"work_id": work_id, "story_world_id": story_world_id},
            "state": _state_dict(state)}


@tool("search_supervoid", title="Search SUPERVOID", kind=ToolKind.READ_ONLY,
      description="Search works and manuscripts you are authorised to see.",
      input_schema=obj({"q": STR, "limit": INT}, required=["q"]))
def search_supervoid(session, principal, args):
    q = (args.get("q") or "").strip()
    if not q:
        raise MCPToolError("Empty query.", code="invalid_args")
    limit = min(int(args.get("limit") or 20), 50)
    like = f"%{q}%"
    works = session.exec(
        select(Work).where(or_(Work.title.ilike(like), Work.synopsis.ilike(like),
                               Work.genre.ilike(like))).limit(limit * 2)
    ).all()
    vis_works = [w for w in works
                 if _admin(principal) or _can(session, principal, PermissionScope.VIEW_PROJECT, work_id=w.id)][:limit]
    mss = session.exec(
        select(Manuscript).where(or_(Manuscript.title.ilike(like), Manuscript.synopsis.ilike(like))).limit(limit * 2)
    ).all()
    vis_ms = [m for m in mss
              if _admin(principal) or _can(session, principal, PermissionScope.VIEW_PROJECT, work_id=m.work_id)][:limit]
    return {
        "works": [{"id": w.id, "title": w.title, "status": w.status.value} for w in vis_works],
        "manuscripts": [{"id": m.id, "title": m.title, "work_id": m.work_id} for m in vis_ms],
    }


def _entity_work_ids(session: Session, entity_id: str) -> list[str]:
    from app.models import ManuscriptEntityLink

    links = session.exec(
        select(ManuscriptEntityLink).where(ManuscriptEntityLink.entity_id == entity_id)
    ).all()
    work_ids = set()
    for ln in links:
        m = session.get(Manuscript, ln.manuscript_id)
        if m and m.work_id:
            work_ids.add(m.work_id)
    return list(work_ids)


def _entity_context(session, principal, ident: str, *, kind: Optional[EntityKind] = None) -> dict:
    entity = session.get(KnowledgeEntity, ident)
    if entity is None:
        entity = session.exec(select(KnowledgeEntity).where(KnowledgeEntity.slug == ident)).first()
    if entity is None:
        entity = session.exec(select(KnowledgeEntity).where(KnowledgeEntity.name == ident)).first()
    if entity is None:
        raise MCPToolError("Entity not found.", code="not_found")
    if kind is not None and entity.kind != kind:
        raise MCPToolError(f"Entity is not a {kind.value}.", code="invalid_args")
    work_ids = _entity_work_ids(session, entity.id)
    if work_ids and not _admin(principal):
        if not any(_can(session, principal, PermissionScope.VIEW_PROJECT, work_id=w) for w in work_ids):
            raise MCPToolError("Not permitted to view this entity's project(s).", code="forbidden")
    from app.services import knowledge as knowledge_svc

    hood = knowledge_svc.neighborhood(session, entity.id, depth=1, limit=40)
    neighbours = []
    if hood is not None:
        for n in getattr(hood, "nodes", []) or []:
            if getattr(n, "id", None) == entity.id:
                continue
            neighbours.append({"id": getattr(n, "id", None), "name": getattr(n, "name", None),
                               "kind": getattr(getattr(n, "kind", None), "value", None)})
    return {"id": entity.id, "name": entity.name, "kind": entity.kind.value,
            "slug": entity.slug, "description": entity.description,
            "neighbours": neighbours[:20]}


@tool("get_entity_context", title="Get entity context", kind=ToolKind.READ_ONLY,
      description="A knowledge-graph entity and its immediate neighbours.",
      input_schema=obj({"entity": opt_str("Entity id, slug or name")}, required=["entity"]))
def get_entity_context(session, principal, args):
    return _entity_context(session, principal, args["entity"])


# === Production ============================================================
def _task_brief(t: ProductionItem) -> dict:
    return {"id": t.id, "title": t.title, "status": t.status.value,
            "priority": getattr(t.priority, "value", None), "work_id": t.work_id,
            "assignee_id": t.assignee_id, "due_date": t.due_date.isoformat() if t.due_date else None}


@tool("get_my_assignments", title="Get my assignments", kind=ToolKind.READ_ONLY,
      description="Production tasks assigned to you (open by default).",
      input_schema=obj({"open_only": {"type": "boolean"}}))
def get_my_assignments(session, principal, args):
    open_only = args.get("open_only", True)
    stmt = select(ProductionItem).where(ProductionItem.assignee_id == principal.user.id)
    rows = session.exec(stmt).all()
    if open_only:
        rows = [t for t in rows if t.status not in _CLOSED_TASK]
    return {"tasks": [_task_brief(t) for t in rows[:100]]}


@tool("get_blocked_tasks", title="Get blocked tasks", kind=ToolKind.READ_ONLY,
      description="Blocked tasks for a work (VIEW_PROJECT) or your own assignments.",
      input_schema=obj({"work_id": opt_str("Work id (optional)")}))
def get_blocked_tasks(session, principal, args):
    from app.services import production as prod_svc

    work_id = args.get("work_id")
    if work_id:
        _require(session, principal, PermissionScope.VIEW_PROJECT, work_id=work_id)
        rows = session.exec(select(ProductionItem).where(ProductionItem.work_id == work_id)).all()
    else:
        rows = session.exec(select(ProductionItem).where(ProductionItem.assignee_id == principal.user.id)).all()
    blocked = [t for t in rows if t.status not in _CLOSED_TASK and prod_svc.is_blocked(session, t)]
    return {"blocked": [_task_brief(t) for t in blocked[:100]]}


@tool("get_pending_approvals", title="Get pending approvals", kind=ToolKind.READ_ONLY,
      description="Approval requests awaiting your decision.",
      input_schema=obj({}))
def get_pending_approvals(session, principal, args):
    from app.models.enums import ApprovalStatus

    rows = session.exec(
        select(ApprovalRequest).where(
            ApprovalRequest.approver_id == principal.user.id,
            ApprovalRequest.status == ApprovalStatus.PENDING,
        )
    ).all()
    return {"approvals": [{"id": a.id, "title": a.title, "target_type": a.target_type,
                           "target_id": a.target_id, "task_id": a.task_id} for a in rows[:100]]}


@tool("inspect_production_progress", title="Inspect production progress", kind=ToolKind.READ_ONLY,
      description="Deterministic task-status rollup for a work.",
      input_schema=obj({"work_id": STR}, required=["work_id"]))
def inspect_production_progress(session, principal, args):
    work_id = args["work_id"]
    _require(session, principal, PermissionScope.VIEW_PROJECT, work_id=work_id)
    rows = session.exec(select(ProductionItem).where(ProductionItem.work_id == work_id)).all()
    counts: dict = {}
    for t in rows:
        counts[t.status.value] = counts.get(t.status.value, 0) + 1
    total = len(rows)
    done = sum(counts.get(s.value, 0) for s in (ProductionItemStatus.DONE, ProductionItemStatus.APPROVED))
    return {"total": total, "by_status": counts,
            "percent_complete": round(100 * done / total, 1) if total else 0.0}


@tool("propose_task", title="Propose a task", kind=ToolKind.PROPOSAL_ONLY, requires_approval=True,
      description="Propose creating a production task (gated; never created directly).",
      input_schema=obj({"work_id": STR, "title": STR, "description": opt_str("Optional"),
                        "priority": opt_str("low|medium|high|urgent"), "assignee_id": opt_str("User id")},
                       required=["work_id", "title"]))
def propose_task(session, principal, args):
    work_id = args["work_id"]
    _require(session, principal, PermissionScope.MANAGE_PRODUCTION, work_id=work_id)
    p = create_action_proposal(
        session, principal, tool_key="create_production_task", target_type="work", target_id=work_id,
        payload={k: args[k] for k in ("title", "description", "priority", "assignee_id") if args.get(k)},
        reason=f"MCP: propose task '{args['title']}'.",
    )
    return {"proposal_id": p.id, "status": p.status.value, "requires_approval": True}


@tool("propose_task_update", title="Propose a task update", kind=ToolKind.PROPOSAL_ONLY, requires_approval=True,
      description="Propose changes to a production task (gated).",
      input_schema=obj({"task_id": STR, "changes": {"type": "object"}}, required=["task_id", "changes"]))
def propose_task_update(session, principal, args):
    task = session.get(ProductionItem, args["task_id"])
    if task is None:
        raise MCPToolError("Task not found.", code="not_found")
    _require(session, principal, PermissionScope.MANAGE_PRODUCTION, work_id=task.work_id)
    p = create_action_proposal(
        session, principal, tool_key="update_production_task", target_type="work", target_id=task.work_id,
        payload={"task_id": task.id, "changes": args.get("changes") or {}},
        reason=f"MCP: propose update to task {task.id}.",
    )
    return {"proposal_id": p.id, "status": p.status.value, "requires_approval": True}


# === Narrative =============================================================
@tool("get_story_world", title="Get story world", kind=ToolKind.READ_ONLY,
      description="A story world's canon summary and status.",
      input_schema=obj({"story_world_id": STR}, required=["story_world_id"]))
def get_story_world(session, principal, args):
    sw = session.get(StoryWorld, args["story_world_id"])
    if sw is None:
        raise MCPToolError("Story world not found.", code="not_found")
    _require(session, principal, PermissionScope.VIEW_PROJECT, story_world_id=sw.id)
    return {"id": sw.id, "name": sw.name, "status": sw.status.value,
            "canon_summary": sw.canon_summary, "description": sw.description}


@tool("get_work_canon", title="Get work canon", kind=ToolKind.READ_ONLY,
      description="A work's canon status and compiled canon digest.",
      input_schema=obj({"work_id": STR}, required=["work_id"]))
def get_work_canon(session, principal, args):
    work = session.get(Work, args["work_id"])
    if work is None:
        raise MCPToolError("Work not found.", code="not_found")
    _require(session, principal, PermissionScope.VIEW_PROJECT, work_id=work.id)
    state = brain.get_project_state(session, work_id=work.id)
    return {"work_id": work.id, "canon_status": work.canon_status.value,
            "canon_digest": state.canon_digest if state else None,
            "canon_facts": (state.structured_state or {}).get("canon_facts") if state else None}


@tool("get_character_context", title="Get character context", kind=ToolKind.READ_ONLY,
      description="A character entity and its immediate relationships.",
      input_schema=obj({"character": opt_str("Entity id, slug or name")}, required=["character"]))
def get_character_context(session, principal, args):
    return _entity_context(session, principal, args["character"], kind=EntityKind.CHARACTER)


@tool("get_location_context", title="Get location context", kind=ToolKind.READ_ONLY,
      description="A place/location entity and its immediate relationships.",
      input_schema=obj({"location": opt_str("Entity id, slug or name")}, required=["location"]))
def get_location_context(session, principal, args):
    return _entity_context(session, principal, args["location"], kind=EntityKind.PLACE)


@tool("get_recent_decisions", title="Get recent decisions", kind=ToolKind.READ_ONLY,
      description="Recent recorded decisions for a project.",
      input_schema=obj({"work_id": opt_str("Work id"), "story_world_id": opt_str("Story world id"),
                        "limit": INT}))
def get_recent_decisions(session, principal, args):
    work_id, story_world_id = _resolve_scope(args)
    _require(session, principal, PermissionScope.VIEW_PROJECT, work_id=work_id, story_world_id=story_world_id)
    rows = brain.list_decisions(session, work_id=work_id, story_world_id=story_world_id,
                                limit=min(int(args.get("limit") or 20), 50))
    return {"decisions": [{"id": d.id, "subject": d.subject, "decision": d.decision,
                           "status": d.status.value} for d in rows]}


@tool("propose_decision", title="Propose a decision", kind=ToolKind.PROPOSAL_ONLY, requires_approval=True,
      description="Record a PROPOSED decision for human review (gated).",
      input_schema=obj({"work_id": opt_str("Work id"), "story_world_id": opt_str("Story world id"),
                        "subject": STR, "decision": STR, "rationale": opt_str("Optional")},
                       required=["subject", "decision"]))
def propose_decision(session, principal, args):
    work_id = args.get("work_id")
    story_world_id = args.get("story_world_id")
    scope = BrainScope.PROJECT if (work_id or story_world_id) else BrainScope.STUDIO
    if work_id or story_world_id:
        _require(session, principal, PermissionScope.EDIT_NARRATIVE, work_id=work_id, story_world_id=story_world_id)
    elif not _admin(principal):
        raise MCPToolError("Studio-scope decisions require admin.", code="forbidden")
    d = brain.create_decision(
        session, scope=scope, subject=args["subject"], decision=args["decision"],
        rationale=args.get("rationale"), proposer_id=principal.user.id,
        work_id=work_id, story_world_id=story_world_id,
    )
    return {"decision_id": d.id, "status": d.status.value}


@tool("propose_canon_change", title="Propose a canon change", kind=ToolKind.PROPOSAL_ONLY, requires_approval=True,
      description="Propose a change to canon as a reviewable decision (gated).",
      input_schema=obj({"work_id": opt_str("Work id"), "story_world_id": opt_str("Story world id"),
                        "summary": STR, "rationale": opt_str("Optional")}, required=["summary"]))
def propose_canon_change(session, principal, args):
    work_id, story_world_id = _resolve_scope(args)
    _require(session, principal, PermissionScope.EDIT_NARRATIVE, work_id=work_id, story_world_id=story_world_id)
    d = brain.create_decision(
        session, scope=BrainScope.PROJECT, subject=f"Canon change: {args['summary'][:120]}",
        decision=args["summary"], rationale=args.get("rationale"), proposer_id=principal.user.id,
        work_id=work_id, story_world_id=story_world_id,
    )
    return {"decision_id": d.id, "status": d.status.value, "kind": "canon_change"}


# === Assets ================================================================
def _asset_visible(session, principal, asset: Asset) -> bool:
    if _admin(principal) or asset.owner_id == principal.user.id:
        return True
    if asset.visibility in (AssetVisibility.SHARED_STUDIO, AssetVisibility.PUBLIC):
        return True
    if asset.work_id and _can(session, principal, PermissionScope.VIEW_PROJECT, work_id=asset.work_id):
        return True
    if asset.story_world_id and _can(session, principal, PermissionScope.VIEW_PROJECT, story_world_id=asset.story_world_id):
        return True
    return False


@tool("search_assets", title="Search assets", kind=ToolKind.READ_ONLY,
      description="Search assets you are authorised to see.",
      input_schema=obj({"q": opt_str("Title contains"), "work_id": opt_str("Work id"), "limit": INT}))
def search_assets(session, principal, args):
    stmt = select(Asset)
    if args.get("work_id"):
        stmt = stmt.where(Asset.work_id == args["work_id"])
    if args.get("q"):
        stmt = stmt.where(Asset.title.ilike(f"%{args['q']}%"))
    rows = session.exec(stmt.limit(200)).all()
    limit = min(int(args.get("limit") or 25), 50)
    visible = [a for a in rows if _asset_visible(session, principal, a)][:limit]
    return {"assets": [{"id": a.id, "title": a.title, "asset_type": a.asset_type.value,
                        "visibility": a.visibility.value, "work_id": a.work_id} for a in visible]}


def _load_asset(session, principal, asset_id: str) -> Asset:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise MCPToolError("Asset not found.", code="not_found")
    if not _asset_visible(session, principal, asset):
        raise MCPToolError("Not permitted to view this asset.", code="forbidden")
    return asset


@tool("inspect_asset_version", title="Inspect asset version", kind=ToolKind.READ_ONLY,
      description="Metadata + approval status for an asset version.",
      input_schema=obj({"asset_id": STR, "version_id": opt_str("Defaults to current")},
                       required=["asset_id"]))
def inspect_asset_version(session, principal, args):
    asset = _load_asset(session, principal, args["asset_id"])
    version_id = args.get("version_id") or asset.current_version_id
    v = session.get(AssetVersion, version_id) if version_id else None
    if v is None or v.asset_id != asset.id:
        raise MCPToolError("Asset version not found.", code="not_found")
    return {"asset_id": asset.id, "version_id": v.id, "version_number": v.version_number,
            "approval_status": v.approval_status.value, "mime_type": v.mime_type,
            "checksum": v.checksum, "is_current": v.id == asset.current_version_id}


@tool("inspect_provenance", title="Inspect provenance", kind=ToolKind.READ_ONLY,
      description="Provenance (human/AI origin) for an asset version.",
      input_schema=obj({"asset_id": STR, "version_id": STR}, required=["asset_id", "version_id"]))
def inspect_provenance(session, principal, args):
    from app.models import ProvenanceRecord

    asset = _load_asset(session, principal, args["asset_id"])
    v = session.get(AssetVersion, args["version_id"])
    if v is None or v.asset_id != asset.id:
        raise MCPToolError("Asset version not found.", code="not_found")
    prov = session.exec(
        select(ProvenanceRecord).where(ProvenanceRecord.asset_version_id == v.id)
    ).first()
    if prov is None:
        return {"asset_id": asset.id, "version_id": v.id, "provenance": None}
    return {"asset_id": asset.id, "version_id": v.id, "provenance": {
        "kind": prov.kind.value, "provider": prov.provider, "base_model": prov.base_model,
        "responsible_user_id": prov.responsible_user_id,
        "commercial_use_review": getattr(prov.commercial_use_review, "value", None)}}


@tool("inspect_licence", title="Inspect licence", kind=ToolKind.READ_ONLY,
      description="Licence records and warnings for an asset.",
      input_schema=obj({"asset_id": STR}, required=["asset_id"]))
def inspect_licence(session, principal, args):
    from app.models import LicenceRecord

    asset = _load_asset(session, principal, args["asset_id"])
    rows = session.exec(select(LicenceRecord).where(LicenceRecord.asset_id == asset.id)).all()
    warnings = [w for w in asset_svc.licence_warnings(session)
                if getattr(w, "asset_id", None) == asset.id]
    return {"asset_id": asset.id,
            "licences": [{"id": lr.id, "licence_type": lr.licence_type.value,
                          "review_state": lr.review_state.value,
                          "expiration_date": lr.expiration_date.isoformat() if lr.expiration_date else None}
                         for lr in rows],
            "warning_count": len(warnings)}


@tool("propose_asset_link", title="Propose an asset link", kind=ToolKind.PROPOSAL_ONLY, requires_approval=True,
      description="Propose linking an asset to a character/location/page (gated).",
      input_schema=obj({"asset_id": STR, "target_type": STR, "target_id": STR, "role": opt_str("Optional")},
                       required=["asset_id", "target_type", "target_id"]))
def propose_asset_link(session, principal, args):
    asset = session.get(Asset, args["asset_id"])
    if asset is None:
        raise MCPToolError("Asset not found.", code="not_found")
    if not (_admin(principal)
            or _can(session, principal, PermissionScope.UPLOAD_ASSETS, work_id=asset.work_id, story_world_id=asset.story_world_id)
            or _can(session, principal, PermissionScope.EDIT_VISUAL_ASSETS, work_id=asset.work_id, story_world_id=asset.story_world_id)):
        raise MCPToolError("Not permitted to link this asset.", code="forbidden")
    p = create_action_proposal(
        session, principal, tool_key="link_asset", target_type="asset", target_id=asset.id,
        payload={"target_type": args["target_type"], "target_id": args["target_id"], "role": args.get("role")},
        reason=f"MCP: propose asset link {asset.id} -> {args['target_type']}:{args['target_id']}.",
    )
    return {"proposal_id": p.id, "status": p.status.value, "requires_approval": True}


# === Publishing and rights =================================================
def _published_for(session, work_id: str):
    from app.models import PublishedWork

    return session.exec(select(PublishedWork).where(PublishedWork.source_work_id == work_id)).first()


@tool("inspect_publication_readiness", title="Inspect publication readiness", kind=ToolKind.READ_ONLY,
      description="Validation status for publishing a work to the public reader.",
      input_schema=obj({"work_id": STR}, required=["work_id"]))
def inspect_publication_readiness(session, principal, args):
    from app.services import curation as curation_svc

    work_id = args["work_id"]
    _require(session, principal, PermissionScope.VIEW_PROJECT, work_id=work_id)
    pub = _published_for(session, work_id)
    if pub is None:
        return {"work_id": work_id, "projected": False,
                "note": "Not yet projected to the public reader."}
    report = curation_svc.validate_for_publication(session, pub)
    return {"work_id": work_id, "projected": True, "published_status": pub.status.value,
            "ok": report.get("ok"), "errors": report.get("errors"), "warnings": report.get("warnings"),
            "issues": report.get("issues", [])[:20]}


@tool("inspect_rights", title="Inspect rights", kind=ToolKind.READ_ONLY,
      description="Rights records and warnings for a work (requires MANAGE_RIGHTS).",
      input_schema=obj({"work_id": STR}, required=["work_id"]))
def inspect_rights(session, principal, args):
    work_id = args["work_id"]
    _require(session, principal, PermissionScope.MANAGE_RIGHTS, work_id=work_id)
    rows = session.exec(select(Rights).where(Rights.work_id == work_id)).all()
    warnings = rights_svc.rights_warnings(session, work_id=work_id)
    return {"work_id": work_id,
            "rights": [{"id": r.id, "territory": r.territory, "language": r.language,
                        "rights_holder": r.rights_holder,
                        "exclusivity": getattr(r.exclusivity, "value", None)} for r in rows],
            "warnings": [getattr(w, "message", str(w)) for w in warnings][:20]}


@tool("prepare_distribution_checklist", title="Prepare distribution checklist", kind=ToolKind.READ_ONLY,
      description="A readiness checklist (validation + rights + licence warnings).",
      input_schema=obj({"work_id": STR}, required=["work_id"]))
def prepare_distribution_checklist(session, principal, args):
    from app.services import curation as curation_svc

    work_id = args["work_id"]
    _require(session, principal, PermissionScope.VIEW_PROJECT, work_id=work_id)
    checklist = []
    pub = _published_for(session, work_id)
    if pub is None:
        checklist.append({"item": "public_projection", "ok": False,
                          "detail": "Work is not projected to the public reader."})
    else:
        report = curation_svc.validate_for_publication(session, pub)
        checklist.append({"item": "publication_validation", "ok": report.get("ok"),
                          "detail": f"{report.get('errors')} errors, {report.get('warnings')} warnings"})
    if _can(session, principal, PermissionScope.MANAGE_RIGHTS, work_id=work_id):
        rw = rights_svc.rights_warnings(session, work_id=work_id)
        checklist.append({"item": "rights", "ok": len(rw) == 0,
                          "detail": f"{len(rw)} rights warning(s)"})
    return {"work_id": work_id, "checklist": checklist}


@tool("propose_publication", title="Propose publication", kind=ToolKind.PROPOSAL_ONLY, requires_approval=True,
      description="Propose publishing a work (CRITICAL; admin approval required).",
      input_schema=obj({"work_id": STR}, required=["work_id"]))
def propose_publication(session, principal, args):
    work_id = args["work_id"]
    _require(session, principal, PermissionScope.PUBLISH, work_id=work_id)
    p = create_action_proposal(
        session, principal, tool_key="publish_to_public_reader", target_type="work", target_id=work_id,
        payload={"work_id": work_id}, reason="MCP: propose publication.",
        risk_level=AgentRiskLevel.CRITICAL,
    )
    return {"proposal_id": p.id, "status": p.status.value, "requires_approval": True}


@tool("propose_rights_action", title="Propose a rights action", kind=ToolKind.PROPOSAL_ONLY, requires_approval=True,
      description="Propose a rights change (HIGH risk; admin approval required).",
      input_schema=obj({"work_id": STR, "action": STR, "details": {"type": "object"}},
                       required=["work_id", "action"]))
def propose_rights_action(session, principal, args):
    work_id = args["work_id"]
    _require(session, principal, PermissionScope.MANAGE_RIGHTS, work_id=work_id)
    p = create_action_proposal(
        session, principal, tool_key="update_rights", target_type="work", target_id=work_id,
        payload={"action": args["action"], "details": args.get("details") or {}},
        reason=f"MCP: propose rights action '{args['action']}'.",
        risk_level=AgentRiskLevel.HIGH,
    )
    return {"proposal_id": p.id, "status": p.status.value, "requires_approval": True}


# === Agent operations ======================================================
@tool("run_supervoid_agent", title="Run a SUPERVOID agent", kind=ToolKind.PROPOSAL_ONLY,
      description="Run a supervised agent (produces findings + gated proposals; no mutations).",
      input_schema=obj({"agent_key": STR, "target_type": opt_str("e.g. work|manuscript"),
                        "target_id": opt_str("Target id")}, required=["agent_key"]))
def run_supervoid_agent(session, principal, args):
    definition = agent_svc.get_agent(args["agent_key"])
    if definition is None:
        raise MCPToolError("Agent not found.", code="not_found")
    target_type = args.get("target_type")
    target_id = args.get("target_id")
    work_id, story_world_id = _work_of(session, target_type, target_id)
    for perm in definition.required_permissions:
        try:
            scope = PermissionScope(perm)
        except ValueError:
            continue
        if not _can(session, principal, scope, work_id=work_id, story_world_id=story_world_id):
            raise MCPToolError(f"Missing permission for agent: {perm}", code="forbidden")
    run = agent_svc.run_agent(session, definition=definition, user=principal.user,
                              target_type=target_type, target_id=target_id,
                              correlation_id=principal.request_id)
    session.flush()
    return {"run_id": run.id, "status": run.status.value,
            "finding_count": len(run.findings), "proposal_count": len(run.proposals),
            "model_driven": (run.result or {}).get("model_driven")}


@tool("list_agent_findings", title="List agent findings", kind=ToolKind.READ_ONLY,
      description="Agent findings you are authorised to see.",
      input_schema=obj({"target_id": opt_str("Filter by target"), "resolved": {"type": "boolean"},
                        "limit": INT}))
def list_agent_findings(session, principal, args):
    stmt = select(AgentFinding)
    if args.get("target_id"):
        stmt = stmt.where(AgentFinding.target_id == args["target_id"])
    if args.get("resolved") is not None:
        stmt = stmt.where(AgentFinding.resolved == args["resolved"])
    stmt = stmt.order_by(AgentFinding.created_at.desc()).limit(200)
    rows = session.exec(stmt).all()
    out = []
    for f in rows:
        if not _can_view_target(session, principal, f.target_type, f.target_id):
            continue
        out.append({"id": f.id, "agent_key": f.agent_key, "severity": f.severity.value,
                    "message": f.message, "target_type": f.target_type, "target_id": f.target_id,
                    "resolved": f.resolved})
        if len(out) >= min(int(args.get("limit") or 50), 100):
            break
    return {"findings": out}


@tool("list_action_proposals", title="List action proposals", kind=ToolKind.READ_ONLY,
      description="Pending/other action proposals you are authorised to see.",
      input_schema=obj({"status": opt_str("pending|approved|rejected|executed|failed"), "limit": INT}))
def list_action_proposals(session, principal, args):
    stmt = select(AgentActionProposal)
    if args.get("status"):
        try:
            stmt = stmt.where(AgentActionProposal.status == ProposalStatus(args["status"]))
        except ValueError:
            raise MCPToolError("Invalid status.", code="invalid_args")
    stmt = stmt.order_by(AgentActionProposal.created_at.desc()).limit(200)
    rows = session.exec(stmt).all()
    out = []
    for p in rows:
        if not _can_view_target(session, principal, p.target_type, p.target_id):
            continue
        out.append({"id": p.id, "tool_key": p.tool_key, "action_type": p.action_type,
                    "status": p.status.value, "risk_level": p.risk_level.value,
                    "target_type": p.target_type, "target_id": p.target_id,
                    "requires_approval": p.requires_approval})
        if len(out) >= min(int(args.get("limit") or 50), 100):
            break
    return {"proposals": out}


def _load_proposal(session, proposal_id: str) -> AgentActionProposal:
    p = session.get(AgentActionProposal, proposal_id)
    if p is None:
        raise MCPToolError("Proposal not found.", code="not_found")
    return p


def _ensure_approval_authority(session, principal, proposal) -> None:
    """Verify the mapped SUPERVOID user actually has the approval scope. Always-
    gated (destructive/publishing/rights/external) tools require admin."""
    tool_def = agent_svc.get_tool(proposal.tool_key)
    if tool_def is not None and tool_def.always_requires_approval and not _admin(principal):
        raise MCPToolError("This action requires an administrator's approval.", code="forbidden")
    work_id, story_world_id = _work_of(session, proposal.target_type, proposal.target_id)
    if not _admin(principal) and not _can(session, principal, PermissionScope.APPROVE,
                                          work_id=work_id, story_world_id=story_world_id):
        raise MCPToolError("You do not have approval authority for this project.", code="forbidden")


@tool("approve_proposal", title="Approve a proposal", kind=ToolKind.APPROVAL, requires_approval=True,
      description="Approve a PENDING proposal (verifies your approval scope).",
      input_schema=obj({"proposal_id": STR}, required=["proposal_id"]))
def approve_proposal(session, principal, args):
    p = _load_proposal(session, args["proposal_id"])
    if p.status != ProposalStatus.PENDING:
        raise MCPToolError(f"Proposal is already {p.status.value}.", code="invalid_state")
    _ensure_approval_authority(session, principal, p)
    p.status = ProposalStatus.APPROVED
    p.approved_by_id = principal.user.id
    p.approved_at = utcnow()
    session.add(p)
    return {"proposal_id": p.id, "status": p.status.value}


@tool("reject_proposal", title="Reject a proposal", kind=ToolKind.APPROVAL, requires_approval=True,
      description="Reject a PENDING proposal (verifies your approval scope).",
      input_schema=obj({"proposal_id": STR, "reason": opt_str("Optional")}, required=["proposal_id"]))
def reject_proposal(session, principal, args):
    p = _load_proposal(session, args["proposal_id"])
    if p.status != ProposalStatus.PENDING:
        raise MCPToolError(f"Proposal is already {p.status.value}.", code="invalid_state")
    _ensure_approval_authority(session, principal, p)
    p.status = ProposalStatus.REJECTED
    p.rejected_by_id = principal.user.id
    p.rejected_at = utcnow()
    if args.get("reason"):
        p.error = args["reason"]
    session.add(p)
    return {"proposal_id": p.id, "status": p.status.value}


@tool("execute_approved_proposal", title="Execute an approved proposal", kind=ToolKind.APPROVAL,
      requires_approval=True,
      description="Execute an APPROVED proposal (MCP proposals are recorded, not auto-fired).",
      input_schema=obj({"proposal_id": STR}, required=["proposal_id"]))
def execute_approved_proposal(session, principal, args):
    p = _load_proposal(session, args["proposal_id"])
    if p.status != ProposalStatus.APPROVED:
        raise MCPToolError("Only an approved proposal can be executed.", code="invalid_state")
    _ensure_approval_authority(session, principal, p)
    agent_svc.execute_proposal(session, p, user=principal.user)
    return {"proposal_id": p.id, "status": p.status.value,
            "execution_result": p.execution_result}
