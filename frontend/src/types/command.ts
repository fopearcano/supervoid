// Types for the operational command centre — mirror schemas/command_centre.py.

export interface Metric {
  label: string;
  count: number;
}

export interface AlertItem {
  kind: string;
  title: string;
  detail: string | null;
  severity: string; // info | warning | critical
  due_date: string | null;
  days_remaining: number | null;
  ref_type: string | null;
  ref_id: string | null;
  work_id: string | null;
}

export interface TaskBrief {
  id: string;
  title: string | null;
  work_id: string | null;
  status: string;
  due_date: string | null;
  days_until: number | null;
  detail: string | null;
}

export interface GraphicNovelProgress {
  productions: number;
  pages_total: number;
  pages_complete: number;
  completion_pct: number;
}

export interface StudioOverview {
  story_worlds: number;
  works_total: number;
  active_works: number;
  divisions: Metric[];
  works_by_status: Metric[];
  graphic_novel: GraphicNovelProgress;
  screen_by_status: Metric[];
  adaptation_dossiers: Metric[];
  releases_upcoming: number;
  releases: AlertItem[];
}

export interface MyWork {
  assigned: TaskBrief[];
  overdue: TaskBrief[];
  blocked: TaskBrief[];
  requested_reviews: TaskBrief[];
  approval_queue: AlertItem[];
  counts: Record<string, number>;
}

export interface AgentInbox {
  findings_by_severity: Metric[];
  open_findings: number;
  pending_proposals: AlertItem[];
  failed_runs: AlertItem[];
  recent_completed: AlertItem[];
}

export interface AssetHealth {
  missing_files: AlertItem[];
  incomplete_provenance: AlertItem[];
  expiring_licences: AlertItem[];
  unapproved_versions: AlertItem[];
  public_without_credits: AlertItem[];
  counts: Record<string, number>;
}

export interface BusinessAlerts {
  rights_expiries: AlertItem[];
  contract_deadlines: AlertItem[];
  distribution_readiness: AlertItem[];
  contact_follow_ups: AlertItem[];
  upcoming_releases: AlertItem[];
  counts: Record<string, number>;
}

export interface WorkBrief {
  id: string;
  title: string;
  status: string;
  medium: string | null;
  story_world: string | null;
}

export interface DivisionView {
  division: string;
  works_count: number;
  works: WorkBrief[];
  metrics: Metric[];
}

export interface WorkCommand {
  id: string;
  title: string;
  status: string;
  division: string;
  medium: string | null;
  story_world: string | null;
  narrative: TaskBrief[];
  production: Record<string, number>;
  assets: Record<string, number>;
  collaborators: AlertItem[];
  rights: Record<string, number>;
  editions: AlertItem[];
  adaptations: AlertItem[];
  public_release: AlertItem | null;
  agent_history: AlertItem[];
}
