"""Code-registered agent definitions and their handlers.

Definitions are registered in code (runs and outputs are persisted). Each
handler is a pure function over an ``AgentContext`` (a read-only snapshot plus
the provider completion) that returns findings and/or proposals — it never
mutates the database itself. Read-only agents must return no proposals; the
runner enforces this.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from app.models.enums import AgentMutability, AgentRiskLevel, FindingSeverity


# --- handler I/O ------------------------------------------------------------


@dataclass
class FindingSpec:
    severity: FindingSeverity
    message: str
    category: Optional[str] = None
    evidence: dict = field(default_factory=dict)
    confidence: Optional[float] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None


@dataclass
class ProposalSpec:
    tool_key: str
    payload: dict
    reason: str
    risk_level: Optional[AgentRiskLevel] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None


@dataclass
class AgentOutput:
    findings: list[FindingSpec] = field(default_factory=list)
    proposals: list[ProposalSpec] = field(default_factory=list)
    result: dict = field(default_factory=dict)


@dataclass
class AgentContext:
    target_type: Optional[str]
    target_id: Optional[str]
    snapshot: dict
    completion: dict  # {provider, model, note} from the (dry-run) provider


@dataclass(frozen=True)
class AgentDefinition:
    key: str
    name: str
    description: str
    supported_entity_types: tuple[str, ...]
    required_permissions: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    mutability: AgentMutability
    default_provider: str
    default_model: Optional[str]
    enabled: bool
    handler: Callable[[AgentContext], AgentOutput]


_AGENTS: dict[str, AgentDefinition] = {}


def _register(defn: AgentDefinition) -> AgentDefinition:
    _AGENTS[defn.key] = defn
    return defn


def get_agent(key: str) -> Optional[AgentDefinition]:
    return _AGENTS.get(key)


def list_agents() -> list[AgentDefinition]:
    return list(_AGENTS.values())


# --- handlers ---------------------------------------------------------------


def _manuscript_consistency(ctx: AgentContext) -> AgentOutput:
    snap = ctx.snapshot
    findings: list[FindingSpec] = []
    if not (snap.get("synopsis") or "").strip():
        findings.append(FindingSpec(
            severity=FindingSeverity.MEDIUM, category="metadata",
            message="Manuscript has no synopsis.", confidence=1.0,
            target_type=ctx.target_type, target_id=ctx.target_id,
        ))
    wc = snap.get("word_count")
    if wc is not None and wc < 1000:
        findings.append(FindingSpec(
            severity=FindingSeverity.LOW, category="length",
            message=f"Word count is low ({wc}).", confidence=0.8,
            target_type=ctx.target_type, target_id=ctx.target_id,
        ))
    if not findings:
        findings.append(FindingSpec(
            severity=FindingSeverity.INFO, category="ok",
            message="No consistency issues detected in the snapshot.",
            target_type=ctx.target_type, target_id=ctx.target_id,
        ))
    return AgentOutput(findings=findings, result={"checked": "manuscript"})


def _work_metadata_advisor(ctx: AgentContext) -> AgentOutput:
    snap = ctx.snapshot
    findings: list[FindingSpec] = []
    proposals: list[ProposalSpec] = []
    if not (snap.get("internal_pitch") or "").strip():
        findings.append(FindingSpec(
            severity=FindingSeverity.LOW, category="metadata",
            message="Work has no internal pitch; one is proposed.",
            target_type=ctx.target_type, target_id=ctx.target_id,
        ))
        proposals.append(ProposalSpec(
            tool_key="update_work_metadata",
            payload={"changes": {
                "internal_pitch": "Draft pitch — review before publishing.",
            }},
            reason="Catalogue completeness: every Work should carry a pitch.",
            risk_level=AgentRiskLevel.MEDIUM,
            target_type=ctx.target_type, target_id=ctx.target_id,
        ))
    return AgentOutput(
        findings=findings, proposals=proposals, result={"analysed": "work"}
    )


def _rights_risk_scanner(ctx: AgentContext) -> AgentOutput:
    findings = [FindingSpec(
        severity=FindingSeverity.INFO, category="rights",
        message="Rights review recommended before any adaptation hand-off.",
        confidence=0.6, target_type=ctx.target_type, target_id=ctx.target_id,
    )]
    return AgentOutput(findings=findings, result={"scanned": "rights"})


def _publishing_readiness(ctx: AgentContext) -> AgentOutput:
    """Proposes publishing — a CRITICAL, always-gated action."""
    proposals = [ProposalSpec(
        tool_key="publish_to_public_reader",
        payload={"work_id": ctx.target_id},
        reason="Work appears ready; publishing requires explicit human approval.",
        risk_level=AgentRiskLevel.CRITICAL,
        target_type=ctx.target_type, target_id=ctx.target_id,
    )]
    findings = [FindingSpec(
        severity=FindingSeverity.INFO, category="publishing",
        message="A publish action has been proposed (approval required).",
        target_type=ctx.target_type, target_id=ctx.target_id,
    )]
    return AgentOutput(findings=findings, proposals=proposals, result={"assessed": "readiness"})


# --- registry ---------------------------------------------------------------

_register(AgentDefinition(
    key="manuscript_consistency",
    name="Manuscript consistency",
    description="Read-only checks over a manuscript snapshot (metadata, length).",
    supported_entity_types=("manuscript",),
    required_permissions=(),
    allowed_tools=("read_entity",),
    mutability=AgentMutability.READ_ONLY,
    default_provider="dry_run",
    default_model=None,
    enabled=True,
    handler=_manuscript_consistency,
))
_register(AgentDefinition(
    key="work_metadata_advisor",
    name="Work metadata advisor",
    description="Suggests catalogue metadata improvements as proposals.",
    supported_entity_types=("work",),
    required_permissions=("edit_narrative",),
    allowed_tools=("read_entity", "update_work_metadata"),
    mutability=AgentMutability.PROPOSE_ONLY,
    default_provider="dry_run",
    default_model=None,
    enabled=True,
    handler=_work_metadata_advisor,
))
_register(AgentDefinition(
    key="rights_risk_scanner",
    name="Rights risk scanner",
    description="Read-only rights-risk observations for a work.",
    supported_entity_types=("work",),
    required_permissions=(),
    allowed_tools=("read_entity",),
    mutability=AgentMutability.READ_ONLY,
    default_provider="dry_run",
    default_model=None,
    enabled=True,
    handler=_rights_risk_scanner,
))
_register(AgentDefinition(
    key="publishing_readiness",
    name="Publishing readiness",
    description="Assesses readiness and proposes a (gated) publish action.",
    supported_entity_types=("work",),
    required_permissions=("publish",),
    allowed_tools=("read_entity", "publish_to_public_reader"),
    mutability=AgentMutability.PROPOSE_ONLY,
    default_provider="dry_run",
    default_model=None,
    enabled=True,
    handler=_publishing_readiness,
))
