"""Deterministic, domain-specific builders for the Brain compiled state.

Every function here is **pure and deterministic**: it derives structured facts
from SQL + existing read services only. The LLM is never consulted — counts,
statuses, deadlines, rights ownership and permissions are computed here, in
Python, from the database.

Determinism rules (so two runs over the same data at the same ``compile_date``
produce a byte-identical structured state — see ``compiler.canonical_json``):

* every query that feeds the state has an explicit ``ORDER BY`` (id / sequence /
  a fixed rank) — never insertion or scan order;
* enums are serialised by ``.value`` and dates by ``.isoformat()`` *inside* the
  builders, so the stored state is plain JSON;
* percentages are rounded; sets are sorted before serialisation;
* any "today"-relative maths uses the pinned ``compile_date``, never wall-clock.

Two registries — :data:`STUDIO_SECTIONS` and :data:`PROJECT_SECTIONS` — map a
section name to its builder, and :data:`EVENT_SECTION_MAP` tells the incremental
compiler which sections a domain event invalidates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.config import settings
from app.models import (
    AdaptationDossier,
    AgentActionProposal,
    AgentFinding,
    ApprovalRequest,
    ApprovalStatus,
    Asset,
    AssetApprovalStatus,
    AssetVersion,
    Contract,
    GraphicNovelPage,
    GraphicNovelPageEntityLink,
    GraphicNovelProduction,
    IntegrationPoint,
    IntegrationRun,
    KnowledgeEntity,
    Manuscript,
    ManuscriptEntityLink,
    ProductionItem,
    ProjectMembership,
    ProvenanceRecord,
    PublishedWork,
    PublishingCalendarEvent,
    Rights,
    ScreenProject,
    StoryWorld,
    Work,
)
from app.models.brain import BrainEvent, BrainMemoryItem, DecisionRecord
from app.models.enums import (
    AdaptationStatus,
    BrainMemoryKind,
    BrainMemoryVerification,
    BrainScope,
    CalendarEventType,
    DecisionStatus,
    EntityKind,
    IntegrationRunStatus,
    ManuscriptLinkRole,
    MembershipStatus,
    ProductionItemStatus,
    ProposalStatus,
    PublishedStatus,
    StoryWorldStatus,
    StreamStatus,
    StudioDivision,
    WorkStatus,
)
from app.services import graphic_novel as gn_service
from app.services import production as production_service
from app.services import rights as rights_service
from app.services import screen as screen_service

# --- bounded list caps (keep structured_state — and thus the summary — small) -
CAP_BLOCKERS = 20
CAP_APPROVALS = 30
CAP_RECENT_CHANGES = 50
CAP_ENTITIES = 200
CAP_FINDINGS = 50
CAP_DECISIONS = 20
CAP_QUESTIONS = 50
CAP_PRIORITIES = 20
CAP_RELEASES = 50
CAP_GENERIC = 50

_ACTIVE_WORK = (
    WorkStatus.PLANNED,
    WorkStatus.IN_DEVELOPMENT,
    WorkStatus.IN_PRODUCTION,
)
_LIVE_WORLD = (StoryWorldStatus.DEVELOPING, StoryWorldStatus.ACTIVE)
_TERMINAL_TASK = (
    ProductionItemStatus.DONE,
    ProductionItemStatus.APPROVED,
    ProductionItemStatus.CANCELLED,
)
_APPROVED_ASSET = (AssetApprovalStatus.APPROVED, AssetApprovalStatus.SUPERSEDED)
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


# --- small deterministic helpers -------------------------------------------
def _count(session: Session, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for clause in where:
        stmt = stmt.where(clause)
    return int(session.exec(stmt).one() or 0)


def _iso(d) -> Optional[str]:
    return d.isoformat() if d is not None else None


def _ev(value) -> Optional[str]:
    """Serialise an enum (or any value) by ``.value`` when present."""
    if value is None:
        return None
    return getattr(value, "value", str(value))


def _group_counts(session: Session, column) -> dict:
    """``{enum_value: count}`` for a column, sorted by key for stable JSON."""
    rows = session.exec(select(column, func.count()).group_by(column)).all()
    out: dict[str, int] = {}
    for key, n in rows:
        if key is None:
            continue
        out[_ev(key)] = int(n)
    return dict(sorted(out.items()))


# === STUDIO BUILDERS =======================================================
def build_studio_identity(session: Session, *, compile_date: date) -> dict:
    divisions = [
        {
            "division": d.value,
            "works": _count(session, Work, Work.primary_division == d),
        }
        for d in StudioDivision
    ]
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "divisions": divisions,
    }


def build_studio_active_story_worlds(session: Session, *, compile_date: date) -> dict:
    rows = session.exec(
        select(StoryWorld)
        .where(StoryWorld.status.in_(_LIVE_WORLD))
        .order_by(StoryWorld.id)
    ).all()
    return {
        "total": _count(session, StoryWorld),
        "active": [
            {"id": w.id, "name": w.name, "slug": w.slug, "status": w.status.value}
            for w in rows
        ],
    }


def build_studio_active_works(session: Session, *, compile_date: date) -> dict:
    rows = session.exec(
        select(Work).where(Work.status.in_(_ACTIVE_WORK)).order_by(Work.id)
    ).all()
    return {
        "total": _count(session, Work),
        "by_status": _group_counts(session, Work.status),
        "active": [
            {
                "id": w.id,
                "title": w.title,
                "work_type": _ev(w.work_type),
                "status": w.status.value,
                "division": _ev(w.primary_division),
                "story_world_id": w.story_world_id,
            }
            for w in rows
        ],
    }


def build_studio_releases(session: Session, *, compile_date: date) -> dict:
    published = session.exec(
        select(PublishedWork)
        .where(PublishedWork.status == PublishedStatus.PUBLISHED)
        .order_by(PublishedWork.publication_date.is_(None), PublishedWork.publication_date, PublishedWork.id)
        .limit(CAP_RELEASES)
    ).all()
    upcoming = session.exec(
        select(PublishingCalendarEvent)
        .where(
            PublishingCalendarEvent.event_type.in_(
                (
                    CalendarEventType.RELEASE,
                    CalendarEventType.PREORDER,
                    CalendarEventType.COVER_REVEAL,
                )
            )
        )
        .where(PublishingCalendarEvent.date >= compile_date)
        .order_by(PublishingCalendarEvent.date, PublishingCalendarEvent.id)
        .limit(CAP_RELEASES)
    ).all()
    return {
        "published": [
            {
                "id": p.id,
                "slug": p.slug,
                "title": p.title,
                "publication_date": _iso(p.publication_date),
                "for_sale": bool(p.for_sale),
            }
            for p in published
        ],
        "upcoming": [
            {
                "id": e.id,
                "title": e.title,
                "event_type": e.event_type.value,
                "date": _iso(e.date),
                "work_id": e.work_id,
            }
            for e in upcoming
        ],
    }


def _is_blocked(session: Session, task: ProductionItem) -> bool:
    return (
        task.status == ProductionItemStatus.BLOCKED
        or production_service.is_blocked(session, task)
    )


def build_studio_major_blockers(session: Session, *, compile_date: date) -> list:
    pool = session.exec(
        select(ProductionItem)
        .where(ProductionItem.status.notin_(_TERMINAL_TASK))
        .order_by(ProductionItem.id)
        .limit(500)
    ).all()
    blocked = [t for t in pool if _is_blocked(session, t)]

    def _rank(t: ProductionItem):
        prio = _ev(t.priority) or "medium"
        prio_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(prio, 2)
        overdue = 0 if (t.due_date and t.due_date < compile_date) else 1
        return (prio_rank, overdue, t.id)

    blocked.sort(key=_rank)
    return [
        {
            "id": t.id,
            "title": t.title,
            "work_id": t.work_id,
            "priority": _ev(t.priority),
            "blocked_reason": t.blocked_reason,
            "due_date": _iso(t.due_date),
            "overdue": bool(t.due_date and t.due_date < compile_date),
        }
        for t in blocked[:CAP_BLOCKERS]
    ]


def _pending_approval_items(session: Session, work_ids: Optional[set] = None) -> dict:
    """Tagged pending approvals, optionally project-scoped to ``work_ids``."""
    items: list[dict] = []
    counts = {"approval_request": 0, "agent_proposal": 0, "publication": 0}

    reqs = session.exec(
        select(ApprovalRequest)
        .where(ApprovalRequest.status == ApprovalStatus.PENDING)
        .order_by(ApprovalRequest.id)
    ).all()
    for a in reqs:
        if work_ids is not None:
            task = session.get(ProductionItem, a.task_id) if a.task_id else None
            if task is None or task.work_id not in work_ids:
                continue
        counts["approval_request"] += 1
        items.append(
            {
                "source": "approval_request",
                "id": a.id,
                "title": a.title or "Approval requested",
                "target": a.target_type,
            }
        )

    proposals = session.exec(
        select(AgentActionProposal)
        .where(AgentActionProposal.status == ProposalStatus.PENDING)
        .order_by(AgentActionProposal.id)
    ).all()
    for p in proposals:
        if work_ids is not None and not _proposal_in_scope(session, p, work_ids):
            continue
        counts["agent_proposal"] += 1
        items.append(
            {
                "source": "agent_proposal",
                "id": p.id,
                "title": f"{p.agent_key}: {p.tool_key}",
                "target": p.target_type,
            }
        )

    pubs = session.exec(
        select(PublicationApproval)
        .where(PublicationApproval.status == PublicationApprovalStatus.PENDING)
        .order_by(PublicationApproval.id)
    ).all()
    for pub in pubs:
        if work_ids is not None:
            pw = session.get(PublishedWork, pub.published_work_id)
            if pw is None or pw.source_work_id not in work_ids:
                continue
        counts["publication"] += 1
        items.append(
            {
                "source": "publication",
                "id": pub.id,
                "title": "Publication approval",
                "target": pub.published_work_id,
            }
        )

    return {"counts": counts, "items": items[:CAP_APPROVALS]}


def _proposal_in_scope(session: Session, proposal, work_ids: set) -> bool:
    if proposal.target_id is None:
        return False
    if proposal.target_type == "work":
        return proposal.target_id in work_ids
    if proposal.target_type == "manuscript":
        m = session.get(Manuscript, proposal.target_id)
        return bool(m and m.work_id in work_ids)
    return False


def build_studio_pending_approvals(session: Session, *, compile_date: date) -> dict:
    return _pending_approval_items(session, work_ids=None)


def _rights_warning_dicts(
    session: Session, *, compile_date: date, work_id: Optional[str] = None
) -> list:
    warnings = rights_service.rights_warnings(
        session, within_days=120, soon_days=30, work_id=work_id, today=compile_date
    )
    return [
        {
            "source": w.source,
            "source_id": w.source_id,
            "work_id": w.work_id,
            "kind": w.kind,
            "due_date": w.due_date,
            "days_remaining": w.days_remaining,
            "status": w.status,
            "scope": w.scope,
            "message": w.message,
        }
        for w in warnings
    ]


def build_studio_rights_warnings(session: Session, *, compile_date: date) -> list:
    return _rights_warning_dicts(session, compile_date=compile_date)[:CAP_GENERIC]


def build_studio_asset_health(session: Session, *, compile_date: date) -> dict:
    from app.services import assets as asset_service

    missing_files = _count(
        session, AssetVersion, AssetVersion.storage_key.like("placeholder:%")
    )
    has_prov = select(ProvenanceRecord.asset_version_id)
    incomplete_provenance = _count(
        session, AssetVersion, AssetVersion.id.notin_(has_prov)
    )
    unapproved_versions = _count(
        session,
        AssetVersion,
        AssetVersion.approval_status.notin_(_APPROVED_ASSET),
    )
    expiring_licences = len(
        asset_service.licence_warnings(session, within_days=60, today=compile_date)
    )
    return {
        "missing_files": missing_files,
        "incomplete_provenance": incomplete_provenance,
        "unapproved_versions": unapproved_versions,
        "expiring_licences": expiring_licences,
        "approval_breakdown": _group_counts(session, AssetVersion.approval_status),
    }


def build_studio_collaborator_load(session: Session, *, compile_date: date) -> dict:
    rows = session.exec(
        select(ProjectMembership)
        .where(ProjectMembership.status == MembershipStatus.ACTIVE)
        .order_by(ProjectMembership.id)
    ).all()
    by_role: dict[str, int] = {}
    by_project: dict[str, int] = {}
    for m in rows:
        role = _ev(m.role)
        by_role[role] = by_role.get(role, 0) + 1
        if m.work_id:
            key = f"work:{m.work_id}"
        elif m.story_world_id:
            key = f"world:{m.story_world_id}"
        else:
            key = "unscoped"
        by_project[key] = by_project.get(key, 0) + 1
    return {
        "total_active": len(rows),
        "by_role": dict(sorted(by_role.items())),
        "by_project": dict(sorted(by_project.items())),
    }


def build_studio_integration_health(session: Session, *, compile_date: date) -> list:
    from app.services.integrations.service import config_status

    points = session.exec(select(IntegrationPoint).order_by(IntegrationPoint.id)).all()
    out = []
    for p in points:
        try:
            missing = sorted(config_status(p).get("missing_config", []))
        except Exception:
            missing = []
        failed = _count(
            session,
            IntegrationRun,
            IntegrationRun.integration_point_id == p.id,
            IntegrationRun.status == IntegrationRunStatus.FAILED,
        )
        pending = _count(
            session,
            IntegrationRun,
            IntegrationRun.integration_point_id == p.id,
            IntegrationRun.status == IntegrationRunStatus.PENDING_APPROVAL,
        )
        out.append(
            {
                "point_id": p.id,
                "name": p.name,
                "type": _ev(p.type),
                "status": _ev(p.status),
                "enabled": bool(p.enabled),
                "adapter_key": p.adapter_key,
                "missing_config": missing,
                "failed_runs": failed,
                "pending_runs": pending,
            }
        )
    return out


def build_studio_strategic_priorities(session: Session, *, compile_date: date) -> list:
    decisions = session.exec(
        select(DecisionRecord)
        .where(
            DecisionRecord.scope == BrainScope.STUDIO,
            DecisionRecord.status == DecisionStatus.APPROVED,
            DecisionRecord.superseded_by_id.is_(None),
        )
        .order_by(DecisionRecord.id)
    ).all()
    memory = session.exec(
        select(BrainMemoryItem)
        .where(
            BrainMemoryItem.scope == BrainScope.STUDIO,
            BrainMemoryItem.kind.in_(
                (BrainMemoryKind.COMMITMENT, BrainMemoryKind.PROCEDURE)
            ),
            BrainMemoryItem.verification == BrainMemoryVerification.VERIFIED,
        )
        .order_by(BrainMemoryItem.id)
    ).all()
    out = [
        {"kind": "decision", "id": d.id, "subject": d.subject, "decision": d.decision}
        for d in decisions
    ]
    out += [
        {"kind": _ev(m.kind), "id": m.id, "content": m.content} for m in memory
    ]
    return out[:CAP_PRIORITIES]


# === PROJECT CONTEXT + BUILDERS ============================================
@dataclass
class ProjectCtx:
    work: Optional[Work]
    story_world: Optional[StoryWorld]
    work_id: Optional[str]
    story_world_id: Optional[str]
    compile_date: date
    to_seq: int


def _world_work_ids(session: Session, story_world_id: str) -> list[str]:
    return list(
        session.exec(
            select(Work.id).where(Work.story_world_id == story_world_id).order_by(Work.id)
        ).all()
    )


def _scope_work_ids(session: Session, ctx: ProjectCtx) -> list[str]:
    if ctx.work_id:
        return [ctx.work_id]
    return _world_work_ids(session, ctx.story_world_id)


def build_project_identity(session: Session, ctx: ProjectCtx) -> dict:
    if ctx.work:
        w = ctx.work
        return {
            "scope": "work",
            "id": w.id,
            "title": w.title,
            "subtitle": w.subtitle,
            "work_type": _ev(w.work_type),
            "genre": w.genre,
            "status": w.status.value,
            "canon_status": _ev(w.canon_status),
            "author_id": w.author_id,
            "story_world_id": w.story_world_id,
            "story_series_id": w.story_series_id,
        }
    sw = ctx.story_world
    return {
        "scope": "story_world",
        "id": sw.id,
        "name": sw.name,
        "slug": sw.slug,
        "status": sw.status.value,
        "owner_id": sw.owner_id,
        "parent_id": sw.parent_id,
    }


def build_project_work_storyworld(session: Session, ctx: ProjectCtx) -> dict:
    if ctx.work:
        world = (
            session.get(StoryWorld, ctx.work.story_world_id)
            if ctx.work.story_world_id
            else None
        )
        return {
            "story_world_id": ctx.work.story_world_id,
            "story_world_name": world.name if world else None,
            "story_series_id": ctx.work.story_series_id,
        }
    works = session.exec(
        select(Work).where(Work.story_world_id == ctx.story_world_id).order_by(Work.id)
    ).all()
    return {
        "works": [
            {"id": w.id, "title": w.title, "status": w.status.value} for w in works
        ]
    }


def build_project_medium_division(session: Session, ctx: ProjectCtx) -> dict:
    if ctx.work:
        return {
            "medium": _ev(ctx.work.primary_medium),
            "division": _ev(ctx.work.primary_division),
        }
    return {"medium": None, "division": None}


def _lead_manuscript(session: Session, work_id: str) -> Optional[Manuscript]:
    return session.exec(
        select(Manuscript).where(Manuscript.work_id == work_id).order_by(Manuscript.id)
    ).first()


def build_project_canonical_synopsis(session: Session, ctx: ProjectCtx) -> dict:
    if ctx.work:
        synopsis = ctx.work.synopsis
        if not synopsis:
            lead = _lead_manuscript(session, ctx.work_id)
            synopsis = lead.synopsis if lead else None
        return {"synopsis": synopsis, "logline": ctx.work.internal_pitch}
    sw = ctx.story_world
    return {"synopsis": sw.description, "logline": sw.canon_summary}


def _scoped_decisions(session: Session, ctx: ProjectCtx):
    stmt = select(DecisionRecord).where(
        DecisionRecord.status == DecisionStatus.APPROVED,
        DecisionRecord.superseded_by_id.is_(None),
    )
    if ctx.work_id:
        stmt = stmt.where(DecisionRecord.work_id == ctx.work_id)
    else:
        stmt = stmt.where(DecisionRecord.story_world_id == ctx.story_world_id)
    return session.exec(stmt.order_by(DecisionRecord.id)).all()


def _scoped_memory(session: Session, ctx: ProjectCtx, kinds: tuple):
    stmt = select(BrainMemoryItem).where(
        BrainMemoryItem.kind.in_(kinds),
        BrainMemoryItem.verification == BrainMemoryVerification.VERIFIED,
    )
    if ctx.work_id:
        stmt = stmt.where(BrainMemoryItem.work_id == ctx.work_id)
    else:
        stmt = stmt.where(BrainMemoryItem.story_world_id == ctx.story_world_id)
    return session.exec(stmt.order_by(BrainMemoryItem.id)).all()


def build_project_canon_facts(session: Session, ctx: ProjectCtx) -> dict:
    if ctx.work:
        canon_status = _ev(ctx.work.canon_status)
        canon_summary = None
    else:
        canon_status = ctx.story_world.status.value
        canon_summary = ctx.story_world.canon_summary
    decisions = _scoped_decisions(session, ctx)
    facts = _scoped_memory(
        session, ctx, (BrainMemoryKind.FACT, BrainMemoryKind.DECISION)
    )
    return {
        "canon_status": canon_status,
        "canon_summary": canon_summary,
        "decisions": [
            {"id": d.id, "subject": d.subject, "decision": d.decision}
            for d in decisions[:CAP_DECISIONS]
        ],
        "facts": [
            {"id": m.id, "content": m.content} for m in facts[:CAP_DECISIONS]
        ],
    }


def _entity_ids_for_works(session: Session, work_ids: list[str]) -> set:
    if not work_ids:
        return set()
    ids: set[str] = set()
    ms_ids = list(
        session.exec(
            select(Manuscript.id).where(Manuscript.work_id.in_(work_ids))
        ).all()
    )
    if ms_ids:
        ids.update(
            session.exec(
                select(ManuscriptEntityLink.entity_id).where(
                    ManuscriptEntityLink.manuscript_id.in_(ms_ids)
                )
            ).all()
        )
    prods = list(
        session.exec(
            select(GraphicNovelProduction.id).where(
                GraphicNovelProduction.work_id.in_(work_ids)
            )
        ).all()
    )
    if prods:
        page_ids = list(
            session.exec(
                select(GraphicNovelPage.id).where(
                    GraphicNovelPage.sequence_id.is_not(None)
                )
            ).all()
        )
        # Page→production is a multi-hop; scope via page entity links that belong
        # to pages of these productions. Resolve pages per production deterministically.
        prod_page_ids: list[str] = []
        for pid in prods:
            prod_page_ids.extend(p.id for p in gn_service.pages_for_production(session, pid))
        if prod_page_ids:
            ids.update(
                session.exec(
                    select(GraphicNovelPageEntityLink.entity_id).where(
                        GraphicNovelPageEntityLink.page_id.in_(prod_page_ids)
                    )
                ).all()
            )
    return ids


def _entities_of_kind(session: Session, entity_ids: set, kind: EntityKind) -> list:
    if not entity_ids:
        return []
    rows = session.exec(
        select(KnowledgeEntity)
        .where(KnowledgeEntity.id.in_(entity_ids), KnowledgeEntity.kind == kind)
        .order_by(KnowledgeEntity.id)
    ).all()
    return [
        {"id": e.id, "name": e.name, "slug": e.slug}
        for e in rows[:CAP_ENTITIES]
    ]


def build_project_characters(session: Session, ctx: ProjectCtx) -> list:
    ids = _entity_ids_for_works(session, _scope_work_ids(session, ctx))
    return _entities_of_kind(session, ids, EntityKind.CHARACTER)


def build_project_locations(session: Session, ctx: ProjectCtx) -> list:
    ids = _entity_ids_for_works(session, _scope_work_ids(session, ctx))
    return _entities_of_kind(session, ids, EntityKind.PLACE)


def build_project_creative_phase(session: Session, ctx: ProjectCtx) -> dict:
    if ctx.work:
        lead = _lead_manuscript(session, ctx.work_id)
        editorial = _ev(lead.status) if lead else None
        allowed_next = []
        if lead is not None:
            from app.services import workflow

            allowed_next = sorted(
                s.value for s in workflow.allowed_next_states(lead.status)
            )
        return {
            "work_status": ctx.work.status.value,
            "editorial_phase": editorial,
            "allowed_next": allowed_next,
        }
    return {"world_status": ctx.story_world.status.value}


def build_project_production_hierarchy(session: Session, ctx: ProjectCtx) -> dict:
    work_ids = _scope_work_ids(session, ctx)
    gn = None
    screen = []
    if work_ids:
        prod = session.exec(
            select(GraphicNovelProduction)
            .where(GraphicNovelProduction.work_id.in_(work_ids))
            .order_by(GraphicNovelProduction.id)
        ).first()
        if prod is not None:
            pages = gn_service.pages_for_production(session, prod.id)
            panels = gn_service.panels_for_pages(session, [p.id for p in pages])
            gn = {
                "production_id": prod.id,
                "pages": len(pages),
                "panels": len(panels),
            }
        projects = session.exec(
            select(ScreenProject)
            .where(ScreenProject.source_work_id.in_(work_ids))
            .order_by(ScreenProject.id)
        ).all()
        for sp in projects:
            try:
                breakdown = screen_service.production_breakdown(session, sp)
                scenes = len(breakdown.get("scenes", breakdown.get("scene_rows", [])))
                shots = int(breakdown.get("total_shots", 0))
            except Exception:
                scenes, shots = 0, 0
            screen.append(
                {
                    "project_id": sp.id,
                    "format": _ev(sp.format),
                    "status": _ev(sp.status),
                    "scenes": scenes,
                    "shots": shots,
                }
            )
    tasks_by_status = _task_status_counts(session, ctx)
    return {"graphic_novel": gn, "screen": screen, "tasks_by_status": tasks_by_status}


def _scoped_tasks(session: Session, ctx: ProjectCtx) -> list:
    work_ids = _scope_work_ids(session, ctx)
    clauses = []
    if work_ids:
        clauses.append(ProductionItem.work_id.in_(work_ids))
    if ctx.story_world_id:
        clauses.append(ProductionItem.story_world_id == ctx.story_world_id)
    if not clauses:
        return []
    from sqlalchemy import or_

    return session.exec(
        select(ProductionItem).where(or_(*clauses)).order_by(ProductionItem.id)
    ).all()


def _task_status_counts(session: Session, ctx: ProjectCtx) -> dict:
    counts: dict[str, int] = {}
    for t in _scoped_tasks(session, ctx):
        key = _ev(t.status)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def build_project_progress(session: Session, ctx: ProjectCtx) -> dict:
    work_ids = _scope_work_ids(session, ctx)
    gn = None
    if work_ids:
        prod = session.exec(
            select(GraphicNovelProduction)
            .where(GraphicNovelProduction.work_id.in_(work_ids))
            .order_by(GraphicNovelProduction.id)
        ).first()
        if prod is not None:
            p = gn_service.production_progress(session, prod)
            gn = {
                "pages_total": p.pages_total,
                "pages_complete": p.pages_complete,
                "panels_total": p.panels_total,
                "panels_approved": p.panels_approved,
                "overall_pct": round(p.overall_pct, 1),
                "panel_approval_pct": round(p.panel_approval_pct, 1),
            }
    tasks = _scoped_tasks(session, ctx)
    open_tasks = [t for t in tasks if t.status not in _TERMINAL_TASK]
    total = len(tasks)
    done = sum(1 for t in tasks if t.status == ProductionItemStatus.DONE)
    blocked = sum(1 for t in open_tasks if _is_blocked(session, t))
    overdue = sum(
        1 for t in open_tasks if t.due_date and t.due_date < ctx.compile_date
    )
    completion_pct = round(100 * done / total) if total else 0
    return {
        "graphic_novel": gn,
        "tasks": {
            "total": total,
            "open": len(open_tasks),
            "done": done,
            "blocked": blocked,
            "overdue": overdue,
            "completion_pct": completion_pct,
        },
    }


def build_project_blocked_tasks(session: Session, ctx: ProjectCtx) -> list:
    open_tasks = [t for t in _scoped_tasks(session, ctx) if t.status not in _TERMINAL_TASK]
    blocked = [t for t in open_tasks if _is_blocked(session, t)]
    blocked.sort(key=lambda t: t.id)
    return [
        {
            "id": t.id,
            "title": t.title,
            "status": _ev(t.status),
            "blocked_reason": t.blocked_reason,
            "due_date": _iso(t.due_date),
        }
        for t in blocked[:CAP_BLOCKERS]
    ]


def build_project_assets(session: Session, ctx: ProjectCtx) -> dict:
    work_ids = _scope_work_ids(session, ctx)
    if not work_ids:
        return {"total": 0, "versions": 0, "unapproved": 0, "incomplete_provenance": 0, "approved": []}
    asset_ids = list(
        session.exec(select(Asset.id).where(Asset.work_id.in_(work_ids))).all()
    )
    versions = (
        session.exec(
            select(AssetVersion)
            .where(AssetVersion.asset_id.in_(asset_ids))
            .order_by(AssetVersion.id)
        ).all()
        if asset_ids
        else []
    )
    has_prov = set(session.exec(select(ProvenanceRecord.asset_version_id)).all())
    approved = [
        {
            "asset_id": v.asset_id,
            "version_id": v.id,
            "version_number": v.version_number,
        }
        for v in versions
        if v.approval_status == AssetApprovalStatus.APPROVED
    ]
    return {
        "total": len(asset_ids),
        "versions": len(versions),
        "unapproved": sum(
            1 for v in versions if v.approval_status not in _APPROVED_ASSET
        ),
        "incomplete_provenance": sum(1 for v in versions if v.id not in has_prov),
        "approved": approved[:CAP_GENERIC],
    }


def _scoped_findings(session: Session, ctx: ProjectCtx) -> list:
    work_id_list = _scope_work_ids(session, ctx)
    work_ids = set(work_id_list)
    ms_ids = (
        set(session.exec(select(Manuscript.id).where(Manuscript.work_id.in_(work_ids))).all())
        if work_ids
        else set()
    )
    # Knowledge-entity findings carry a KnowledgeEntity id, not a manuscript id,
    # so they are matched against the in-scope entity set (same scoping the
    # characters/locations builders use).
    entity_ids = _entity_ids_for_works(session, work_id_list)
    rows = session.exec(
        select(AgentFinding)
        .where(AgentFinding.resolved == False)  # noqa: E712
        .order_by(AgentFinding.id)
    ).all()
    out = []
    for f in rows:
        if f.target_type == "work" and f.target_id in work_ids:
            out.append(f)
        elif f.target_type == "manuscript" and f.target_id in ms_ids:
            out.append(f)
        elif f.target_type == "knowledge_entity" and f.target_id in entity_ids:
            out.append(f)
    return out


def build_project_continuity_findings(session: Session, ctx: ProjectCtx) -> list:
    findings = _scoped_findings(session, ctx)
    findings.sort(key=lambda f: (_SEVERITY_RANK.get(_ev(f.severity), 9), f.id))
    return [
        {
            "id": f.id,
            "severity": _ev(f.severity),
            "category": f.category,
            "message": f.message,
            "target_type": f.target_type,
            "target_id": f.target_id,
        }
        for f in findings[:CAP_FINDINGS]
    ]


def build_project_rights_constraints(session: Session, ctx: ProjectCtx) -> dict:
    work_ids = _scope_work_ids(session, ctx)
    if not work_ids:
        return {"profiles": [], "warnings": []}
    rows = session.exec(
        select(Rights).where(Rights.work_id.in_(work_ids)).order_by(Rights.id)
    ).all()
    profiles = []
    for r in rows:
        signed = _count(
            session, Contract,
            Contract.work_id == r.work_id,
        )
        profiles.append(
            {
                "id": r.id,
                "work_id": r.work_id,
                "territory": r.territory,
                "language": r.language,
                "print": _ev(r.print_rights),
                "ebook": _ev(r.ebook_rights),
                "audiobook": _ev(r.audiobook_rights),
                "film": _ev(r.film_rights),
                "adaptation": _ev(r.adaptation_rights),
                "merchandising": _ev(r.merchandising_rights),
                "exclusivity": _ev(r.exclusivity),
                "holder": r.holder or r.rights_holder,
                "term_end": _iso(r.term_end_date or r.expiration_date),
                "reversion_date": _iso(r.reversion_date),
                "sublicensable": bool(r.sublicensable),
                "adaptation_constraints": r.adaptation_constraints,
                "contracts": signed,
            }
        )
    warnings = []
    for wid in work_ids:
        warnings.extend(_rights_warning_dicts(session, compile_date=ctx.compile_date, work_id=wid))
    return {"profiles": profiles, "warnings": warnings[:CAP_GENERIC]}


def build_project_adaptations(session: Session, ctx: ProjectCtx) -> list:
    work_ids = _scope_work_ids(session, ctx)
    if not work_ids:
        return []
    rows = session.exec(
        select(AdaptationDossier)
        .where(AdaptationDossier.source_work_id.in_(work_ids))
        .order_by(AdaptationDossier.id)
    ).all()
    return [
        {
            "id": d.id,
            "target_medium": _ev(d.target_medium),
            "target_division": _ev(d.target_division),
            "status": _ev(d.status),
            "rights_clearance": _ev(d.rights_clearance),
            "target_work_id": d.target_work_id,
        }
        for d in rows[:CAP_GENERIC]
    ]


def build_project_pending_approvals(session: Session, ctx: ProjectCtx) -> dict:
    return _pending_approval_items(session, work_ids=set(_scope_work_ids(session, ctx)))


def build_project_recent_decisions(session: Session, ctx: ProjectCtx) -> list:
    decisions = _scoped_decisions(session, ctx)
    return [
        {
            "id": d.id,
            "subject": d.subject,
            "decision": d.decision,
            "effective_date": _iso(d.effective_date),
        }
        for d in decisions[:CAP_DECISIONS]
    ]


def build_project_unresolved_questions(session: Session, ctx: ProjectCtx) -> list:
    stmt = select(BrainMemoryItem).where(
        BrainMemoryItem.kind == BrainMemoryKind.UNRESOLVED_QUESTION,
        BrainMemoryItem.verification.notin_(
            (
                BrainMemoryVerification.REJECTED,
                BrainMemoryVerification.SUPERSEDED,
                BrainMemoryVerification.EXPIRED,
            )
        ),
    )
    if ctx.work_id:
        stmt = stmt.where(BrainMemoryItem.work_id == ctx.work_id)
    else:
        stmt = stmt.where(BrainMemoryItem.story_world_id == ctx.story_world_id)
    rows = session.exec(stmt.order_by(BrainMemoryItem.id)).all()
    out = [
        {"source": "memory", "id": m.id, "text": m.content}
        for m in rows
        if m.expires_at is None or m.expires_at.date() > ctx.compile_date
    ]
    for f in _scoped_findings(session, ctx):
        out.append({"source": "finding", "id": f.id, "text": f.message})
    out.sort(key=lambda x: (x["source"], x["id"]))
    return out[:CAP_QUESTIONS]


def build_project_recent_changes(session: Session, ctx: ProjectCtx) -> list:
    from sqlalchemy import or_

    clauses = []
    if ctx.work_id:
        clauses.append(BrainEvent.work_id == ctx.work_id)
        clauses.append(
            (BrainEvent.aggregate_type == "work")
            & (BrainEvent.aggregate_id == ctx.work_id)
        )
    if ctx.story_world_id:
        clauses.append(BrainEvent.story_world_id == ctx.story_world_id)
        clauses.append(
            (BrainEvent.aggregate_type == "story_world")
            & (BrainEvent.aggregate_id == ctx.story_world_id)
        )
    if not clauses:
        return []
    rows = session.exec(
        select(BrainEvent)
        .where(BrainEvent.sequence <= ctx.to_seq, or_(*clauses))
        .order_by(BrainEvent.sequence.desc())
        .limit(CAP_RECENT_CHANGES)
    ).all()
    return [
        {
            "sequence": e.sequence,
            "event_type": e.event_type,
            "aggregate_type": e.aggregate_type,
            "aggregate_id": e.aggregate_id,
            "summary": (e.payload or {}).get("summary"),
            "occurred_at": _iso(e.occurred_at),
        }
        for e in rows
    ]


def build_project_next_priorities(session: Session, ctx: ProjectCtx) -> list:
    out: list[dict] = []
    for t in build_project_blocked_tasks(session, ctx):
        out.append({"kind": "blocked_task", "ref": t["id"], "label": t["title"]})
    rights = build_project_rights_constraints(session, ctx)["warnings"]
    for w in rights:
        if w.get("status") == "overdue":
            out.append({"kind": "rights", "ref": w.get("source_id"), "label": w.get("message")})
    commitments = _scoped_memory(session, ctx, (BrainMemoryKind.COMMITMENT,))
    for m in commitments:
        out.append({"kind": "commitment", "ref": m.id, "label": m.content})
    return out[:CAP_PRIORITIES]


# === registries + section ordering =========================================
StudioBuilder = Callable[..., object]
ProjectBuilder = Callable[..., object]

STUDIO_SECTIONS: dict[str, StudioBuilder] = {
    "identity": build_studio_identity,
    "active_story_worlds": build_studio_active_story_worlds,
    "active_works": build_studio_active_works,
    "releases": build_studio_releases,
    "major_blockers": build_studio_major_blockers,
    "pending_approvals": build_studio_pending_approvals,
    "rights_warnings": build_studio_rights_warnings,
    "asset_health": build_studio_asset_health,
    "collaborator_load": build_studio_collaborator_load,
    "integration_health": build_studio_integration_health,
    "strategic_priorities": build_studio_strategic_priorities,
}
STUDIO_ORDER = list(STUDIO_SECTIONS.keys())

PROJECT_SECTIONS: dict[str, ProjectBuilder] = {
    "identity": build_project_identity,
    "work_storyworld": build_project_work_storyworld,
    "medium_division": build_project_medium_division,
    "canonical_synopsis": build_project_canonical_synopsis,
    "canon_facts": build_project_canon_facts,
    "characters": build_project_characters,
    "locations": build_project_locations,
    "creative_phase": build_project_creative_phase,
    "production_hierarchy": build_project_production_hierarchy,
    "progress": build_project_progress,
    "blocked_tasks": build_project_blocked_tasks,
    "assets_approved_versions": build_project_assets,
    "continuity_findings": build_project_continuity_findings,
    "rights_constraints": build_project_rights_constraints,
    "adaptations": build_project_adaptations,
    "pending_approvals": build_project_pending_approvals,
    "recent_decisions": build_project_recent_decisions,
    "unresolved_questions": build_project_unresolved_questions,
    "recent_changes": build_project_recent_changes,
    "next_priorities": build_project_next_priorities,
}
PROJECT_ORDER = list(PROJECT_SECTIONS.keys())

# Which state sections a domain-event prefix invalidates (incremental rebuilds).
# Keys are the dotted event-type prefix; values are "studio.<section>" /
# "project.<section>". Unknown prefixes fall back to recent_changes only.
EVENT_SECTION_MAP: dict[str, list[str]] = {
    "work.": [
        "studio.active_works", "studio.identity", "studio.collaborator_load",
        "project.identity", "project.work_storyworld", "project.medium_division",
        "project.canonical_synopsis", "project.creative_phase", "project.canon_facts",
    ],
    "story_world.": [
        "studio.active_story_worlds", "project.identity", "project.work_storyworld",
        "project.canon_facts", "project.creative_phase",
    ],
    "story_series.": ["studio.active_works", "project.work_storyworld"],
    "manuscript.": [
        "project.canonical_synopsis", "project.creative_phase", "project.characters",
        "project.locations", "project.canon_facts",
    ],
    "knowledge_entity.": ["project.characters", "project.locations", "project.canon_facts"],
    "knowledge_relationship.": ["project.characters", "project.locations", "project.canon_facts"],
    "task.": [
        "studio.major_blockers", "project.production_hierarchy", "project.progress",
        "project.blocked_tasks", "project.next_priorities",
    ],
    "approval.": ["studio.pending_approvals", "project.pending_approvals"],
    "asset.": [
        "studio.asset_health", "project.assets_approved_versions",
        "project.production_hierarchy", "project.progress",
    ],
    "provenance.": ["studio.asset_health", "project.assets_approved_versions"],
    "licence.": ["studio.asset_health", "studio.rights_warnings", "project.rights_constraints"],
    "page.": [
        "project.production_hierarchy", "project.progress", "project.blocked_tasks",
        "project.assets_approved_versions", "project.characters", "project.locations",
    ],
    "panel.": [
        "project.production_hierarchy", "project.progress", "project.blocked_tasks",
        "project.assets_approved_versions",
    ],
    "screen_project.": [
        "studio.active_works", "project.production_hierarchy", "project.progress",
        "project.adaptations",
    ],
    "scene.": ["project.production_hierarchy", "project.progress", "project.characters", "project.locations"],
    "shot.": [
        "project.production_hierarchy", "project.progress", "project.blocked_tasks",
        "project.assets_approved_versions",
    ],
    "rights.": [
        "studio.rights_warnings", "studio.major_blockers",
        "project.rights_constraints", "project.next_priorities",
    ],
    "contract.": [
        "studio.rights_warnings", "project.rights_constraints",
        "project.next_priorities",
    ],
    "adaptation.": ["studio.active_works", "project.adaptations", "project.rights_constraints"],
    "collaborator.": ["studio.collaborator_load"],
    "publication.": ["studio.releases", "studio.pending_approvals", "project.pending_approvals"],
    "agent.": [
        "studio.pending_approvals", "studio.major_blockers", "project.pending_approvals",
        "project.continuity_findings", "project.unresolved_questions", "project.next_priorities",
    ],
    "decision.": [
        "studio.strategic_priorities", "project.canon_facts", "project.recent_decisions",
        "project.next_priorities",
    ],
    # Verified / retired durable memory feeds canon_facts (FACT, DECISION),
    # unresolved_questions, and next_priorities (COMMITMENT) at project scope,
    # and strategic_priorities at studio scope.
    "memory.": [
        "studio.strategic_priorities", "project.canon_facts",
        "project.unresolved_questions", "project.next_priorities",
    ],
    # A completed conversation turn enqueues the memory-analysis job (handled by
    # the consumer's analyzer branch); it intentionally invalidates NO compiled
    # section. Mapped to [] so the coverage invariant stays explicit.
    "conversation.": [],
}

# recent_changes is always rebuilt for any scoped event (it is time/sequence based).
_PROJECT_ALWAYS = {"recent_changes"}


def affected_sections(events: list, scope: str) -> set:
    """Return the set of section names (for ``scope`` = 'studio' | 'project')
    invalidated by ``events``. Unknown event prefixes touch only the always-on
    sections so a new event type never silently drops coverage."""
    out: set[str] = set()
    prefix_seen = set()
    for ev in events:
        etype = getattr(ev, "event_type", "") or ""
        prefix = etype.split(".")[0] + "." if "." in etype else etype
        prefix_seen.add(prefix)
        mapped = EVENT_SECTION_MAP.get(prefix)
        if mapped is None:
            continue
        for entry in mapped:
            ns, _, name = entry.partition(".")
            if ns == scope:
                out.add(name)
    if scope == "project" and events:
        out |= _PROJECT_ALWAYS
    return out


# Resolved late to avoid an import cycle at module load.
from app.models import PublicationApproval  # noqa: E402
from app.models.enums import PublicationApprovalStatus  # noqa: E402
