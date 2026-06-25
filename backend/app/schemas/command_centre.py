"""Read schemas for the operational command centre.

The command centre aggregates every SUPERVOID domain into one archival surface.
Shapes are deliberately small and generic (counts + short top-N lists) so the
one-person workflow loads fast and sections can be disclosed progressively.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Metric(BaseModel):
    """A labelled count (status / severity / division roll-ups)."""

    label: str
    count: int


class AlertItem(BaseModel):
    """A generic, actionable line for inbox / health / alert lists."""

    kind: str
    title: str
    detail: Optional[str] = None
    severity: str = "info"  # info | warning | critical
    due_date: Optional[str] = None
    days_remaining: Optional[int] = None
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None
    work_id: Optional[str] = None


class TaskBrief(BaseModel):
    id: str
    title: Optional[str] = None
    work_id: Optional[str] = None
    status: str
    due_date: Optional[str] = None
    days_until: Optional[int] = None
    detail: Optional[str] = None


# --- 1. studio overview ----------------------------------------------------


class GraphicNovelProgress(BaseModel):
    productions: int
    pages_total: int
    pages_complete: int
    completion_pct: float


class StudioOverview(BaseModel):
    story_worlds: int
    works_total: int
    active_works: int
    divisions: list[Metric]
    works_by_status: list[Metric]
    graphic_novel: GraphicNovelProgress
    screen_by_status: list[Metric]
    adaptation_dossiers: list[Metric]
    releases_upcoming: int
    releases: list[AlertItem]


# --- 2. my work ------------------------------------------------------------


class MyWork(BaseModel):
    assigned: list[TaskBrief]
    overdue: list[TaskBrief]
    blocked: list[TaskBrief]
    requested_reviews: list[TaskBrief]
    approval_queue: list[AlertItem]
    counts: dict[str, int]


# --- 3. agent inbox --------------------------------------------------------


class AgentInbox(BaseModel):
    findings_by_severity: list[Metric]
    open_findings: int
    pending_proposals: list[AlertItem]
    failed_runs: list[AlertItem]
    recent_completed: list[AlertItem]


# --- 4. asset health -------------------------------------------------------


class AssetHealth(BaseModel):
    missing_files: list[AlertItem]
    incomplete_provenance: list[AlertItem]
    expiring_licences: list[AlertItem]
    unapproved_versions: list[AlertItem]
    public_without_credits: list[AlertItem]
    counts: dict[str, int]


# --- 5. business alerts ----------------------------------------------------


class BusinessAlerts(BaseModel):
    rights_expiries: list[AlertItem]
    contract_deadlines: list[AlertItem]
    distribution_readiness: list[AlertItem]
    contact_follow_ups: list[AlertItem]
    upcoming_releases: list[AlertItem]
    counts: dict[str, int]


# --- 6. division views -----------------------------------------------------


class WorkBrief(BaseModel):
    id: str
    title: str
    status: str
    medium: Optional[str] = None
    story_world: Optional[str] = None


class DivisionView(BaseModel):
    division: str
    works_count: int
    works: list[WorkBrief]
    metrics: list[Metric]


# --- 7. work command page --------------------------------------------------


class WorkCommand(BaseModel):
    id: str
    title: str
    status: str
    division: str
    medium: Optional[str]
    story_world: Optional[str]

    narrative: list[TaskBrief]  # manuscripts (title + status)
    production: dict[str, int]  # open / done / blocked / overdue
    assets: dict[str, int]  # total / unapproved / incomplete_provenance
    collaborators: list[AlertItem]  # role + member
    rights: dict[str, int]  # profiles / warnings
    editions: list[AlertItem]  # format + distribution status
    adaptations: list[AlertItem]  # target medium + status
    public_release: Optional[AlertItem]  # published status, if any
    agent_history: list[AlertItem]  # recent runs targeting this work
