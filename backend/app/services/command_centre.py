"""The operational command centre: cross-domain aggregation.

Read-only roll-ups over every SUPERVOID domain — studio overview, the current
user's work, the agent inbox, asset health, business alerts, division views and
a per-work command page. Reuses the rights / licence / provenance / production
services rather than re-deriving their logic. Top-N lists keep it light for the
one-person studio; counts support progressive disclosure.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from app.models import (
    AdaptationDossier,
    AgentActionProposal,
    AgentFinding,
    AgentRun,
    AgentRunStatus,
    ApprovalRequest,
    ApprovalStatus,
    Asset,
    AssetApprovalStatus,
    AssetVersion,
    Contact,
    DistributionStatus,
    Edition,
    GraphicNovelPage,
    GraphicNovelProduction,
    Manuscript,
    ProductionItem,
    ProductionItemStatus,
    ProjectMembership,
    ProvenanceRecord,
    PublicMediaAsset,
    PublishedStatus,
    PublishedWork,
    PublishingCalendarEvent,
    ProposalStatus,
    Rights,
    ScreenProject,
    StoryWorld,
    StreamStatus,
    StudioDivision,
    User,
    Work,
    WorkStatus,
)
from app.models.enums import CalendarEventType, MembershipStatus
from app.schemas.command_centre import (
    AgentInbox,
    AlertItem,
    AssetHealth,
    BusinessAlerts,
    DivisionView,
    GraphicNovelProgress,
    Metric,
    MyWork,
    StudioOverview,
    TaskBrief,
    WorkBrief,
    WorkCommand,
)
from app.services import assets as asset_service
from app.services import production as production_service
from app.services import rights as rights_service

LIMIT = 10
_ACTIVE_WORK = (WorkStatus.PLANNED, WorkStatus.IN_DEVELOPMENT, WorkStatus.IN_PRODUCTION)
_TERMINAL = (
    ProductionItemStatus.DONE,
    ProductionItemStatus.APPROVED,
    ProductionItemStatus.CANCELLED,
)
_RISK_SEVERITY = {"critical": "critical", "high": "critical", "medium": "warning", "low": "info"}
_WARN_SEVERITY = {"overdue": "critical", "due_soon": "warning", "upcoming": "info"}


def _count(session: Session, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for clause in where:
        stmt = stmt.where(clause)
    return session.exec(stmt).one()


def _group(session: Session, column) -> list[Metric]:
    rows = session.exec(select(column, func.count()).group_by(column)).all()
    out = []
    for key, n in rows:
        if key is None:
            continue
        out.append(Metric(label=getattr(key, "value", str(key)), count=n))
    return out


def _iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


# --- 1. studio overview ----------------------------------------------------


def studio_overview(session: Session) -> StudioOverview:
    today = date.today()
    pages_total = _count(session, GraphicNovelPage)
    pages_complete = _count(
        session, GraphicNovelPage, GraphicNovelPage.final_status == StreamStatus.COMPLETE
    )
    gn = GraphicNovelProgress(
        productions=_count(session, GraphicNovelProduction),
        pages_total=pages_total,
        pages_complete=pages_complete,
        completion_pct=round(pages_complete / pages_total * 100, 1) if pages_total else 0.0,
    )

    releases: list[AlertItem] = []
    events = session.exec(
        select(PublishingCalendarEvent)
        .where(
            PublishingCalendarEvent.event_type.in_(
                (CalendarEventType.RELEASE, CalendarEventType.PREORDER, CalendarEventType.COVER_REVEAL)
            )
        )
        .where(PublishingCalendarEvent.date >= today)
        .order_by(PublishingCalendarEvent.date.asc())
        .limit(LIMIT)
    ).all()
    for ev in events:
        days = (ev.date - today).days
        releases.append(AlertItem(
            kind=ev.event_type.value, title=ev.title, due_date=_iso(ev.date),
            days_remaining=days, severity="warning" if days <= 14 else "info",
            ref_type="calendar_event", ref_id=ev.id, work_id=ev.work_id,
        ))

    return StudioOverview(
        story_worlds=_count(session, StoryWorld),
        works_total=_count(session, Work),
        active_works=_count(session, Work, Work.status.in_(_ACTIVE_WORK)),
        divisions=[
            Metric(label=d.value, count=_count(session, Work, Work.primary_division == d))
            for d in StudioDivision
        ],
        works_by_status=_group(session, Work.status),
        graphic_novel=gn,
        screen_by_status=_group(session, ScreenProject.status),
        adaptation_dossiers=_group(session, AdaptationDossier.status),
        releases_upcoming=len(releases),
        releases=releases,
    )


# --- 2. my work ------------------------------------------------------------


def _task_brief(task: ProductionItem, today: date) -> TaskBrief:
    return TaskBrief(
        id=task.id, title=task.title, work_id=task.work_id, status=task.status.value,
        due_date=_iso(task.due_date),
        days_until=(task.due_date - today).days if task.due_date else None,
        detail=task.blocked_reason,
    )


def my_work(session: Session, user: User) -> MyWork:
    today = date.today()
    mine_or_unassigned = (
        (ProductionItem.assignee_id == user.id) | (ProductionItem.assignee_id.is_(None))
    )
    open_clause = ProductionItem.status.notin_(_TERMINAL)

    assigned = session.exec(
        select(ProductionItem)
        .where(ProductionItem.assignee_id == user.id, open_clause)
        .order_by(ProductionItem.due_date.is_(None), ProductionItem.due_date.asc())
        .limit(LIMIT)
    ).all()
    overdue = session.exec(
        select(ProductionItem)
        .where(mine_or_unassigned, open_clause)
        .where(ProductionItem.due_date.is_not(None), ProductionItem.due_date < today)
        .order_by(ProductionItem.due_date.asc())
        .limit(LIMIT)
    ).all()
    # Blocked: explicit BLOCKED status, or open tasks with unmet dependencies.
    open_pool = session.exec(
        select(ProductionItem).where(mine_or_unassigned, open_clause).limit(200)
    ).all()
    blocked = [
        t for t in open_pool
        if t.status == ProductionItemStatus.BLOCKED or production_service.is_blocked(session, t)
    ][:LIMIT]
    requested_reviews = session.exec(
        select(ProductionItem)
        .where(ProductionItem.reviewer_id == user.id)
        .where(ProductionItem.status == ProductionItemStatus.IN_REVIEW)
        .limit(LIMIT)
    ).all()

    approvals = session.exec(
        select(ApprovalRequest)
        .where(ApprovalRequest.approver_id == user.id)
        .where(ApprovalRequest.status == ApprovalStatus.PENDING)
        .order_by(ApprovalRequest.created_at.desc())
        .limit(LIMIT)
    ).all()
    approval_queue = [
        AlertItem(
            kind="approval", title=a.title or "Approval requested",
            detail=a.target_type, severity="warning",
            ref_type="approval_request", ref_id=a.id,
        )
        for a in approvals
    ]

    return MyWork(
        assigned=[_task_brief(t, today) for t in assigned],
        overdue=[_task_brief(t, today) for t in overdue],
        blocked=[_task_brief(t, today) for t in blocked],
        requested_reviews=[_task_brief(t, today) for t in requested_reviews],
        approval_queue=approval_queue,
        counts={
            "assigned": len(assigned), "overdue": len(overdue),
            "blocked": len(blocked), "requested_reviews": len(requested_reviews),
            "approval_queue": len(approval_queue),
        },
    )


# --- 3. agent inbox --------------------------------------------------------


def agent_inbox(session: Session) -> AgentInbox:
    open_by_sev = session.exec(
        select(AgentFinding.severity, func.count())
        .where(AgentFinding.resolved == False)  # noqa: E712
        .group_by(AgentFinding.severity)
    ).all()
    findings_by_severity = [
        Metric(label=getattr(k, "value", str(k)), count=n) for k, n in open_by_sev if k
    ]
    open_findings = _count(session, AgentFinding, AgentFinding.resolved == False)  # noqa: E712

    proposals = session.exec(
        select(AgentActionProposal)
        .where(AgentActionProposal.status == ProposalStatus.PENDING)
        .order_by(AgentActionProposal.created_at.desc())
        .limit(LIMIT)
    ).all()
    pending_proposals = [
        AlertItem(
            kind="proposal", title=f"{p.agent_key}: {p.tool_key}",
            detail=p.reason, severity=_RISK_SEVERITY.get(p.risk_level.value, "info"),
            ref_type="agent_proposal", ref_id=p.id,
            work_id=p.target_id if p.target_type == "work" else None,
        )
        for p in proposals
    ]

    failed = session.exec(
        select(AgentRun)
        .where(AgentRun.status == AgentRunStatus.FAILED)
        .order_by(AgentRun.created_at.desc())
        .limit(LIMIT)
    ).all()
    failed_runs = [
        AlertItem(kind="run", title=r.agent_key, detail=r.error, severity="critical",
                  ref_type="agent_run", ref_id=r.id,
                  work_id=r.target_id if r.target_type == "work" else None)
        for r in failed
    ]

    completed = session.exec(
        select(AgentRun)
        .where(AgentRun.status == AgentRunStatus.SUCCEEDED)
        .order_by(AgentRun.completed_at.desc())
        .limit(LIMIT)
    ).all()
    recent_completed = [
        AlertItem(kind="run", title=r.agent_key, detail="analysis complete",
                  due_date=_iso(r.completed_at.date() if r.completed_at else None),
                  ref_type="agent_run", ref_id=r.id,
                  work_id=r.target_id if r.target_type == "work" else None)
        for r in completed
    ]

    return AgentInbox(
        findings_by_severity=findings_by_severity,
        open_findings=open_findings,
        pending_proposals=pending_proposals,
        failed_runs=failed_runs,
        recent_completed=recent_completed,
    )


# --- 4. asset health -------------------------------------------------------


def asset_health(session: Session) -> AssetHealth:
    def _asset_title(version: AssetVersion) -> str:
        asset = session.get(Asset, version.asset_id)
        return asset.title if asset else version.asset_id

    missing_versions = session.exec(
        select(AssetVersion)
        .where(AssetVersion.storage_key.like("placeholder:%"))
        .order_by(AssetVersion.created_at.desc())
        .limit(LIMIT)
    ).all()
    missing_files = [
        AlertItem(kind="missing_file", title=_asset_title(v),
                  detail="No file uploaded yet (placeholder).", severity="warning",
                  ref_type="asset_version", ref_id=v.id)
        for v in missing_versions
    ]
    missing_count = _count(session, AssetVersion, AssetVersion.storage_key.like("placeholder:%"))

    # Incomplete provenance: versions with no provenance record.
    has_prov = select(ProvenanceRecord.asset_version_id)
    no_prov = session.exec(
        select(AssetVersion).where(AssetVersion.id.notin_(has_prov)).limit(LIMIT)
    ).all()
    incomplete_provenance = [
        AlertItem(kind="incomplete_provenance", title=_asset_title(v),
                  detail="No provenance record.", severity="warning",
                  ref_type="asset_version", ref_id=v.id)
        for v in no_prov
    ]
    incomplete_count = _count(session, AssetVersion, AssetVersion.id.notin_(has_prov))

    lic_warnings = asset_service.licence_warnings(session, within_days=60)

    def _lic_title(asset_id: str) -> str:
        asset = session.get(Asset, asset_id)
        return asset.title if asset else asset_id

    expiring_licences = [
        AlertItem(kind="licence", title=_lic_title(w.asset_id),
                  detail=f"{w.licence_type} · {w.status}",
                  severity="critical" if w.status == "expired" else "warning",
                  due_date=w.expiration_date, days_remaining=w.days_remaining,
                  ref_type="asset", ref_id=w.asset_id)
        for w in lic_warnings[:LIMIT]
    ]

    unapproved = session.exec(
        select(AssetVersion)
        .where(AssetVersion.approval_status.notin_(
            (AssetApprovalStatus.APPROVED, AssetApprovalStatus.SUPERSEDED)
        ))
        .order_by(AssetVersion.created_at.desc())
        .limit(LIMIT)
    ).all()
    unapproved_versions = [
        AlertItem(kind="unapproved", title=_asset_title(v),
                  detail=v.approval_status.value, severity="info",
                  ref_type="asset_version", ref_id=v.id)
        for v in unapproved
    ]
    unapproved_count = _count(
        session, AssetVersion,
        AssetVersion.approval_status.notin_(
            (AssetApprovalStatus.APPROVED, AssetApprovalStatus.SUPERSEDED)
        ),
    )

    # Public assets without complete credits.
    public_without_credits: list[AlertItem] = []
    pub_works = session.exec(
        select(PublishedWork).where(PublishedWork.status == PublishedStatus.PUBLISHED)
    ).all()
    for w in pub_works:
        missing = [c for c, v in (("author", w.author_credit), ("artist", w.artist_credit)) if not v]
        if missing:
            public_without_credits.append(AlertItem(
                kind="public_credits", title=w.title,
                detail=f"Missing {', '.join(missing)} credit.", severity="warning",
                ref_type="published_work", ref_id=w.id,
            ))
    media_no_credit = session.exec(
        select(PublicMediaAsset)
        .where(PublicMediaAsset.public_visibility == True)  # noqa: E712
        .where(PublicMediaAsset.credits.is_(None))
        .limit(LIMIT)
    ).all()
    for m in media_no_credit:
        public_without_credits.append(AlertItem(
            kind="public_credits", title=m.title, detail="Public media has no credits.",
            severity="info", ref_type="public_media", ref_id=m.id,
        ))

    return AssetHealth(
        missing_files=missing_files,
        incomplete_provenance=incomplete_provenance,
        expiring_licences=expiring_licences,
        unapproved_versions=unapproved_versions,
        public_without_credits=public_without_credits[:LIMIT],
        counts={
            "missing_files": missing_count,
            "incomplete_provenance": incomplete_count,
            "expiring_licences": len(lic_warnings),
            "unapproved_versions": unapproved_count,
            "public_without_credits": len(public_without_credits),
        },
    )


# --- 5. business alerts ----------------------------------------------------


def business_alerts(session: Session) -> BusinessAlerts:
    today = date.today()
    warnings = rights_service.rights_warnings(session, within_days=120)

    def _warn_item(w) -> AlertItem:
        return AlertItem(
            kind=w.kind, title=w.message, severity=_WARN_SEVERITY.get(w.status, "info"),
            due_date=w.due_date, days_remaining=w.days_remaining,
            ref_type=w.source, ref_id=w.source_id, work_id=w.work_id,
        )

    rights_expiries = [_warn_item(w) for w in warnings if w.source != "contract"][:LIMIT]
    contract_deadlines = [_warn_item(w) for w in warnings if w.source == "contract"][:LIMIT]

    editions = session.exec(
        select(Edition)
        .where(Edition.distribution_status.in_(
            (DistributionStatus.IN_PREP, DistributionStatus.READY, DistributionStatus.SUBMITTED)
        ))
        .order_by(Edition.publication_date.is_(None), Edition.publication_date.asc())
        .limit(LIMIT)
    ).all()
    distribution_readiness = [
        AlertItem(kind="edition", title=e.title or "Edition",
                  detail=f"{e.format.value} · {e.distribution_status.value}",
                  severity="info", due_date=_iso(e.publication_date),
                  ref_type="edition", ref_id=e.id, work_id=e.work_id)
        for e in editions
    ]

    contacts = session.exec(
        select(Contact)
        .where(Contact.follow_up_date.is_not(None))
        .where(Contact.do_not_contact == False)  # noqa: E712
        .order_by(Contact.follow_up_date.asc())
        .limit(LIMIT)
    ).all()
    contact_follow_ups = [
        AlertItem(kind="contact", title=c.full_name, detail="Follow up",
                  due_date=_iso(c.follow_up_date),
                  days_remaining=(c.follow_up_date - today).days if c.follow_up_date else None,
                  severity="warning" if c.follow_up_date and c.follow_up_date <= today else "info",
                  ref_type="contact", ref_id=c.id)
        for c in contacts
    ]

    rel_events = session.exec(
        select(PublishingCalendarEvent)
        .where(PublishingCalendarEvent.event_type.in_(
            (CalendarEventType.RELEASE, CalendarEventType.PREORDER)
        ))
        .where(PublishingCalendarEvent.date >= today)
        .order_by(PublishingCalendarEvent.date.asc())
        .limit(LIMIT)
    ).all()
    upcoming_releases = [
        AlertItem(kind=ev.event_type.value, title=ev.title, due_date=_iso(ev.date),
                  days_remaining=(ev.date - today).days,
                  severity="warning" if (ev.date - today).days <= 14 else "info",
                  ref_type="calendar_event", ref_id=ev.id, work_id=ev.work_id)
        for ev in rel_events
    ]

    return BusinessAlerts(
        rights_expiries=rights_expiries,
        contract_deadlines=contract_deadlines,
        distribution_readiness=distribution_readiness,
        contact_follow_ups=contact_follow_ups,
        upcoming_releases=upcoming_releases,
        counts={
            "rights_expiries": sum(1 for w in warnings if w.source != "contract"),
            "contract_deadlines": sum(1 for w in warnings if w.source == "contract"),
            "distribution_readiness": len(distribution_readiness),
            "contact_follow_ups": len(contact_follow_ups),
            "upcoming_releases": len(upcoming_releases),
        },
    )


# --- 6. division views -----------------------------------------------------


def _work_brief(session: Session, work: Work) -> WorkBrief:
    world = session.get(StoryWorld, work.story_world_id) if work.story_world_id else None
    return WorkBrief(
        id=work.id, title=work.title, status=work.status.value,
        medium=work.primary_medium.value if work.primary_medium else None,
        story_world=world.name if world else None,
    )


def _division_view(session: Session, division: StudioDivision) -> DivisionView:
    works = session.exec(
        select(Work).where(Work.primary_division == division)
        .order_by(Work.created_at.desc()).limit(LIMIT)
    ).all()
    works_count = _count(session, Work, Work.primary_division == division)

    metrics: list[Metric] = [Metric(label="works", count=works_count)]
    work_ids = list(session.exec(
        select(Work.id).where(Work.primary_division == division)
    ).all())
    if division == StudioDivision.PUBLISHING:
        gn = _count(session, GraphicNovelProduction,
                    GraphicNovelProduction.work_id.in_(work_ids)) if work_ids else 0
        metrics.append(Metric(label="graphic novels", count=gn))
        metrics.append(Metric(label="editions",
                              count=_count(session, Edition, Edition.work_id.in_(work_ids)) if work_ids else 0))
    elif division == StudioDivision.PICTURES:
        metrics.append(Metric(label="screen projects", count=_count(session, ScreenProject)))
        metrics.append(Metric(label="adaptation dossiers",
                              count=_count(session, AdaptationDossier,
                                           AdaptationDossier.target_division == division)))

    return DivisionView(
        division=division.value, works_count=works_count,
        works=[_work_brief(session, w) for w in works], metrics=metrics,
    )


def division_views(session: Session) -> list[DivisionView]:
    return [_division_view(session, d) for d in (
        StudioDivision.PUBLISHING, StudioDivision.PICTURES,
        StudioDivision.INTERACTIVE, StudioDivision.CROSS_MEDIA,
    )]


# --- 7. work command page --------------------------------------------------


def work_command(session: Session, work_id: str) -> WorkCommand:
    work = session.get(Work, work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")
    today = date.today()
    world = session.get(StoryWorld, work.story_world_id) if work.story_world_id else None

    manuscripts = session.exec(
        select(Manuscript).where(Manuscript.work_id == work_id)
    ).all()
    narrative = [
        TaskBrief(id=m.id, title=m.title, work_id=work_id, status=m.status.value)
        for m in manuscripts
    ]

    tasks = session.exec(
        select(ProductionItem).where(ProductionItem.work_id == work_id)
    ).all()
    open_tasks = [t for t in tasks if t.status not in _TERMINAL]
    production = {
        "total": len(tasks),
        "open": len(open_tasks),
        "done": sum(1 for t in tasks if t.status == ProductionItemStatus.DONE),
        "blocked": sum(
            1 for t in open_tasks
            if t.status == ProductionItemStatus.BLOCKED or production_service.is_blocked(session, t)
        ),
        "overdue": sum(1 for t in open_tasks if t.due_date and t.due_date < today),
    }

    asset_ids = list(session.exec(select(Asset.id).where(Asset.work_id == work_id)).all())
    versions = session.exec(
        select(AssetVersion).where(AssetVersion.asset_id.in_(asset_ids))
    ).all() if asset_ids else []
    has_prov = set(session.exec(select(ProvenanceRecord.asset_version_id)).all())
    assets = {
        "total": len(asset_ids),
        "versions": len(versions),
        "unapproved": sum(
            1 for v in versions
            if v.approval_status not in (AssetApprovalStatus.APPROVED, AssetApprovalStatus.SUPERSEDED)
        ),
        "incomplete_provenance": sum(1 for v in versions if v.id not in has_prov),
    }

    memberships = session.exec(
        select(ProjectMembership)
        .where(ProjectMembership.work_id == work_id)
        .where(ProjectMembership.status == MembershipStatus.ACTIVE)
        .limit(LIMIT)
    ).all()
    collaborators = []
    for m in memberships:
        member = session.get(User, m.user_id)
        collaborators.append(AlertItem(
            kind="member", title=member.full_name if member else m.user_id,
            detail=m.role.value, ref_type="membership", ref_id=m.id,
        ))

    rights_count = _count(session, Rights, Rights.work_id == work_id)
    rights_warn = len(rights_service.rights_warnings(session, work_id=work_id))

    editions = session.exec(select(Edition).where(Edition.work_id == work_id)).all()
    edition_items = [
        AlertItem(kind="edition", title=e.title or e.format.value,
                  detail=f"{e.format.value} · {e.distribution_status.value}",
                  due_date=_iso(e.publication_date), ref_type="edition", ref_id=e.id)
        for e in editions
    ]

    dossiers = session.exec(
        select(AdaptationDossier).where(AdaptationDossier.source_work_id == work_id)
    ).all()
    adaptations = [
        AlertItem(kind="adaptation", title=d.target_medium.value, detail=d.status.value,
                  ref_type="adaptation_dossier", ref_id=d.id)
        for d in dossiers
    ]

    pub = session.exec(
        select(PublishedWork).where(PublishedWork.source_work_id == work_id)
    ).first()
    public_release = AlertItem(
        kind="public", title=pub.title, detail=pub.status.value,
        severity="info" if pub.status == PublishedStatus.PUBLISHED else "warning",
        ref_type="published_work", ref_id=pub.id,
    ) if pub else None

    runs = session.exec(
        select(AgentRun)
        .where(AgentRun.target_type == "work", AgentRun.target_id == work_id)
        .order_by(AgentRun.created_at.desc())
        .limit(LIMIT)
    ).all()
    agent_history = [
        AlertItem(kind="run", title=r.agent_key, detail=r.status.value,
                  severity="critical" if r.status == AgentRunStatus.FAILED else "info",
                  ref_type="agent_run", ref_id=r.id)
        for r in runs
    ]

    return WorkCommand(
        id=work.id, title=work.title, status=work.status.value,
        division=work.primary_division.value,
        medium=work.primary_medium.value if work.primary_medium else None,
        story_world=world.name if world else None,
        narrative=narrative, production=production, assets=assets,
        collaborators=collaborators,
        rights={"profiles": rights_count, "warnings": rights_warn},
        editions=edition_items, adaptations=adaptations,
        public_release=public_release, agent_history=agent_history,
    )
