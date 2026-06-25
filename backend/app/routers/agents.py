"""The supervised studio-agent framework API (private, Agent Centre).

Registry (definitions + tools), run + history, findings inbox, and proposal
approval / rejection / execution. Read-only analysis runs immediately; mutations
arrive as gated proposals; destructive / publishing / rights / external actions
require admin approval before they can be executed. The existing manuscript AI
endpoints and AIInsight records are untouched.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, func, select

from app.auth import AUTHED, get_current_user
from app.db import get_session
from app.models import (
    AgentActionProposal,
    AgentFinding,
    AgentRun,
    AgentRunStatus,
    FindingSeverity,
    PromptTemplate,
    PromptTemplateVersion,
    ProposalStatus,
    User,
    UserRole,
)
from app.models.base import utcnow
from app.models.enums import PermissionScope
from app.schemas.agent import (
    AgentDefinitionRead,
    AgentFindingRead,
    AgentProposalRead,
    AgentRunDetail,
    AgentRunRead,
    PromptTemplateCreate,
    PromptTemplateRead,
    PromptVersionCreate,
    PromptVersionRead,
    ProposalRejectRequest,
    RunRequest,
    ToolRead,
)
from app.services import agents as agent_svc
from app.services import policy
from app.utils import (
    Page,
    PageParams,
    get_or_404,
    page_params,
    paginate,
)

router = APIRouter(tags=["agents"], dependencies=AUTHED)


# --- read builders ---------------------------------------------------------


def _run_read(session: Session, run: AgentRun) -> AgentRunRead:
    read = AgentRunRead.model_validate(run)
    read.finding_count = session.exec(
        select(func.count()).select_from(AgentFinding).where(AgentFinding.run_id == run.id)
    ).one()
    read.proposal_count = session.exec(
        select(func.count()).select_from(AgentActionProposal).where(
            AgentActionProposal.run_id == run.id
        )
    ).one()
    return read


def _run_detail(run: AgentRun) -> AgentRunDetail:
    detail = AgentRunDetail.model_validate(run)
    detail.findings = [AgentFindingRead.model_validate(f) for f in run.findings]
    detail.proposals = [AgentProposalRead.model_validate(p) for p in run.proposals]
    detail.finding_count = len(run.findings)
    detail.proposal_count = len(run.proposals)
    return detail


def _check_permissions(session, user, definition, target_type, target_id) -> None:
    """Enforce an agent's declared permissions via the policy service (ADMIN
    bypasses; project scopes are checked against the target work)."""
    for perm in definition.required_permissions:
        try:
            scope = PermissionScope(perm)
        except ValueError:
            continue
        work_id = target_id if target_type == "work" else None
        if not policy.can(session, user, scope, work_id=work_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission for agent: {perm}",
            )


# --- registry --------------------------------------------------------------


@router.get("/agents", response_model=list[AgentDefinitionRead])
def list_agent_definitions() -> list[AgentDefinitionRead]:
    return [
        AgentDefinitionRead(
            key=d.key, name=d.name, description=d.description,
            supported_entity_types=list(d.supported_entity_types),
            required_permissions=list(d.required_permissions),
            allowed_tools=list(d.allowed_tools), mutability=d.mutability,
            default_provider=d.default_provider, default_model=d.default_model,
            enabled=d.enabled,
        )
        for d in agent_svc.list_agents()
    ]


@router.get("/agents/tools", response_model=list[ToolRead])
def list_agent_tools() -> list[ToolRead]:
    return [
        ToolRead(
            key=t.key, name=t.name, description=t.description, kind=t.kind,
            risk_level=t.risk_level,
            required_permissions=list(t.required_permissions),
            always_requires_approval=t.always_requires_approval,
        )
        for t in agent_svc.list_tools()
    ]


# --- run -------------------------------------------------------------------


@router.post("/agents/{key}/run", response_model=AgentRunDetail, status_code=201)
def run_agent(
    key: str,
    payload: RunRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AgentRunDetail:
    definition = agent_svc.get_agent(key)
    if definition is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    _check_permissions(session, user, definition, payload.target_type, payload.target_id)
    run = agent_svc.run_agent(
        session, definition=definition, user=user,
        target_type=payload.target_type, target_id=payload.target_id,
    )
    session.commit()
    session.refresh(run)
    return _run_detail(run)


@router.get("/agent-runs", response_model=Page[AgentRunRead])
def list_runs(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    agent_key: Optional[str] = Query(default=None),
    status_: Optional[AgentRunStatus] = Query(default=None, alias="status"),
    target_id: Optional[str] = Query(default=None),
) -> Page[AgentRunRead]:
    stmt = select(AgentRun)
    if agent_key is not None:
        stmt = stmt.where(AgentRun.agent_key == agent_key)
    if status_ is not None:
        stmt = stmt.where(AgentRun.status == status_)
    if target_id is not None:
        stmt = stmt.where(AgentRun.target_id == target_id)
    stmt = stmt.order_by(AgentRun.created_at.desc())
    items, total = paginate(session, stmt, params)
    return Page[AgentRunRead](
        items=[_run_read(session, r) for r in items],
        total=total, skip=params.skip, limit=params.limit,
    )


@router.get("/agent-runs/{run_id}", response_model=AgentRunDetail)
def get_run(run_id: str, session: Session = Depends(get_session)) -> AgentRunDetail:
    run = get_or_404(session, AgentRun, run_id, name="AgentRun")
    return _run_detail(run)


@router.post("/agent-runs/{run_id}/retry", response_model=AgentRunDetail, status_code=201)
def retry_run(
    run_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AgentRunDetail:
    original = get_or_404(session, AgentRun, run_id, name="AgentRun")
    definition = agent_svc.get_agent(original.agent_key)
    if definition is None:
        raise HTTPException(status_code=409, detail="Agent no longer registered")
    _check_permissions(session, user, definition, original.target_type, original.target_id)
    run = agent_svc.retry_run(session, original, definition=definition, user=user)
    session.commit()
    session.refresh(run)
    return _run_detail(run)


# --- findings inbox --------------------------------------------------------


@router.get("/agent-findings", response_model=Page[AgentFindingRead])
def list_findings(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    agent_key: Optional[str] = Query(default=None),
    severity: Optional[FindingSeverity] = Query(default=None),
    resolved: Optional[bool] = Query(default=None),
    target_id: Optional[str] = Query(default=None),
) -> Page[AgentFindingRead]:
    stmt = select(AgentFinding)
    if agent_key is not None:
        stmt = stmt.where(AgentFinding.agent_key == agent_key)
    if severity is not None:
        stmt = stmt.where(AgentFinding.severity == severity)
    if resolved is not None:
        stmt = stmt.where(AgentFinding.resolved == resolved)
    if target_id is not None:
        stmt = stmt.where(AgentFinding.target_id == target_id)
    stmt = stmt.order_by(AgentFinding.created_at.desc())
    items, total = paginate(session, stmt, params)
    return Page[AgentFindingRead](
        items=[AgentFindingRead.model_validate(f) for f in items],
        total=total, skip=params.skip, limit=params.limit,
    )


@router.post("/agent-findings/{finding_id}/resolve", response_model=AgentFindingRead)
def resolve_finding(
    finding_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AgentFindingRead:
    finding = get_or_404(session, AgentFinding, finding_id, name="AgentFinding")
    finding.resolved = True
    finding.resolved_by_id = user.id
    finding.resolved_at = utcnow()
    session.add(finding)
    session.commit()
    session.refresh(finding)
    return AgentFindingRead.model_validate(finding)


# --- proposals: approve / reject / execute ---------------------------------


@router.get("/agent-proposals", response_model=Page[AgentProposalRead])
def list_proposals(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    status_: Optional[ProposalStatus] = Query(default=None, alias="status"),
    agent_key: Optional[str] = Query(default=None),
) -> Page[AgentProposalRead]:
    stmt = select(AgentActionProposal)
    if status_ is not None:
        stmt = stmt.where(AgentActionProposal.status == status_)
    if agent_key is not None:
        stmt = stmt.where(AgentActionProposal.agent_key == agent_key)
    stmt = stmt.order_by(AgentActionProposal.created_at.desc())
    items, total = paginate(session, stmt, params)
    return Page[AgentProposalRead](
        items=[AgentProposalRead.model_validate(p) for p in items],
        total=total, skip=params.skip, limit=params.limit,
    )


def _load_pending(session: Session, proposal_id: str) -> AgentActionProposal:
    proposal = get_or_404(session, AgentActionProposal, proposal_id, name="AgentActionProposal")
    if proposal.status != ProposalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Proposal is already {proposal.status.value}.",
        )
    return proposal


@router.post("/agent-proposals/{proposal_id}/approve", response_model=AgentProposalRead)
def approve_proposal(
    proposal_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AgentProposalRead:
    proposal = _load_pending(session, proposal_id)
    tool = agent_svc.get_tool(proposal.tool_key)
    # Always-gated categories (destructive / publishing / rights / external)
    # need an admin sign-off.
    if tool is not None and tool.always_requires_approval and user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires an administrator's approval.",
        )
    proposal.status = ProposalStatus.APPROVED
    proposal.approved_by_id = user.id
    proposal.approved_at = utcnow()
    session.add(proposal)
    session.commit()
    session.refresh(proposal)
    return AgentProposalRead.model_validate(proposal)


@router.post("/agent-proposals/{proposal_id}/reject", response_model=AgentProposalRead)
def reject_proposal(
    proposal_id: str,
    payload: ProposalRejectRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AgentProposalRead:
    proposal = _load_pending(session, proposal_id)
    proposal.status = ProposalStatus.REJECTED
    proposal.rejected_by_id = user.id
    proposal.rejected_at = utcnow()
    if payload.reason:
        proposal.error = payload.reason
    session.add(proposal)
    session.commit()
    session.refresh(proposal)
    return AgentProposalRead.model_validate(proposal)


@router.post("/agent-proposals/{proposal_id}/execute", response_model=AgentProposalRead)
def execute_proposal(
    proposal_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AgentProposalRead:
    proposal = get_or_404(session, AgentActionProposal, proposal_id, name="AgentActionProposal")
    agent_svc.execute_proposal(session, proposal, user=user)
    session.commit()
    session.refresh(proposal)
    return AgentProposalRead.model_validate(proposal)


# --- prompt templates (versioned) ------------------------------------------


@router.get("/prompt-templates", response_model=list[PromptTemplateRead])
def list_prompt_templates(session: Session = Depends(get_session)) -> list[PromptTemplateRead]:
    stmt = select(PromptTemplate).order_by(PromptTemplate.key)
    return [PromptTemplateRead.model_validate(t) for t in session.exec(stmt).all()]


@router.post("/prompt-templates", response_model=PromptTemplateRead, status_code=201)
def create_prompt_template(
    payload: PromptTemplateCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PromptTemplateRead:
    existing = session.exec(
        select(PromptTemplate).where(PromptTemplate.key == payload.key)
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Prompt template key already exists")
    template = PromptTemplate(
        key=payload.key, name=payload.name, description=payload.description,
        current_version=1,
    )
    session.add(template)
    session.flush()
    session.add(PromptTemplateVersion(
        template_id=template.id, version=1, body=payload.body, created_by_id=user.id,
    ))
    session.commit()
    session.refresh(template)
    return PromptTemplateRead.model_validate(template)


def _template_by_key(session: Session, key: str) -> PromptTemplate:
    template = session.exec(
        select(PromptTemplate).where(PromptTemplate.key == key)
    ).first()
    if template is None:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    return template


@router.get("/prompt-templates/{key}/versions", response_model=list[PromptVersionRead])
def list_prompt_versions(key: str, session: Session = Depends(get_session)) -> list[PromptVersionRead]:
    template = _template_by_key(session, key)
    stmt = (
        select(PromptTemplateVersion)
        .where(PromptTemplateVersion.template_id == template.id)
        .order_by(PromptTemplateVersion.version.desc())
    )
    return [PromptVersionRead.model_validate(v) for v in session.exec(stmt).all()]


@router.post("/prompt-templates/{key}/versions", response_model=PromptVersionRead, status_code=201)
def add_prompt_version(
    key: str,
    payload: PromptVersionCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PromptVersionRead:
    template = _template_by_key(session, key)
    new_version = template.current_version + 1
    version = PromptTemplateVersion(
        template_id=template.id, version=new_version, body=payload.body,
        notes=payload.notes, created_by_id=user.id,
    )
    template.current_version = new_version
    session.add_all([version, template])
    session.commit()
    session.refresh(version)
    return PromptVersionRead.model_validate(version)


@router.get("/prompt-templates/{key}", response_model=PromptTemplateRead)
def get_prompt_template(key: str, session: Session = Depends(get_session)) -> PromptTemplateRead:
    return PromptTemplateRead.model_validate(_template_by_key(session, key))
