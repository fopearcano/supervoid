// Types for the general production task system (mirrors the backend schemas).

export type ProductionTaskStatus =
  | 'pending'
  | 'todo'
  | 'in_progress'
  | 'blocked'
  | 'in_review'
  | 'changes_requested'
  | 'approved'
  | 'done'
  | 'cancelled';

export type ProductionPriority = 'low' | 'medium' | 'high' | 'critical';

export type ProductionTrack =
  | 'editorial' | 'art' | 'lettering' | 'color' | 'layout' | 'prepress'
  | 'print' | 'script' | 'storyboard' | 'animation' | 'vfx' | 'photography'
  | 'editing' | 'sound' | 'music' | 'engineering' | 'design' | 'qa'
  | 'marketing' | 'production' | 'other';

export type ProductionTaskType =
  | 'task' | 'review' | 'deliverable' | 'approval' | 'bug' | 'research' | 'admin';

export type StudioDivision =
  | 'publishing' | 'pictures' | 'interactive' | 'audio' | 'cross_media';

export type ApprovalStatus =
  | 'pending' | 'approved' | 'rejected' | 'changes_requested' | 'cancelled';

export const STATUS_LABELS: Record<ProductionTaskStatus, string> = {
  pending: 'Pending',
  todo: 'To do',
  in_progress: 'In progress',
  blocked: 'Blocked',
  in_review: 'In review',
  changes_requested: 'Changes requested',
  approved: 'Approved',
  done: 'Done',
  cancelled: 'Cancelled',
};

// The columns shown on the kanban board, in flow order.
export const KANBAN_STATUSES: ProductionTaskStatus[] = [
  'todo',
  'in_progress',
  'blocked',
  'in_review',
  'approved',
  'done',
];

export const PRIORITY_LABELS: Record<ProductionPriority, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  critical: 'Critical',
};

export const PRIORITIES = Object.keys(PRIORITY_LABELS) as ProductionPriority[];

export const TRACK_LABELS: Record<ProductionTrack, string> = {
  editorial: 'Editorial', art: 'Art', lettering: 'Lettering', color: 'Colour',
  layout: 'Layout', prepress: 'Prepress', print: 'Print', script: 'Script',
  storyboard: 'Storyboard', animation: 'Animation', vfx: 'VFX',
  photography: 'Photography', editing: 'Editing', sound: 'Sound',
  music: 'Music', engineering: 'Engineering', design: 'Design', qa: 'QA',
  marketing: 'Marketing', production: 'Production', other: 'Other',
};

export const TRACKS = Object.keys(TRACK_LABELS) as ProductionTrack[];

export const TASK_TYPE_LABELS: Record<ProductionTaskType, string> = {
  task: 'Task', review: 'Review', deliverable: 'Deliverable',
  approval: 'Approval', bug: 'Bug', research: 'Research', admin: 'Admin',
};

export const TASK_TYPES = Object.keys(TASK_TYPE_LABELS) as ProductionTaskType[];

export interface ProductionTask {
  id: string;
  created_at: string;
  updated_at: string;
  title: string | null;
  description: string | null;
  work_id: string | null;
  manuscript_id: string | null;
  story_world_id: string | null;
  division: StudioDivision | null;
  track: ProductionTrack | null;
  task_type: ProductionTaskType;
  priority: ProductionPriority;
  stage: string | null;
  status: ProductionTaskStatus;
  assignee_id: string | null;
  assignee_name: string | null;
  creator_id: string | null;
  creator_name: string | null;
  reviewer_id: string | null;
  reviewer_name: string | null;
  parent_id: string | null;
  milestone_id: string | null;
  start_date: string | null;
  due_date: string | null;
  completed_date: string | null;
  estimated_effort: number | null;
  actual_effort: number | null;
  blocked_reason: string | null;
  acceptance_criteria: string | null;
  deliverable_asset: string | null;
  revision_number: number;
  notes: string | null;
}

export interface ProductionTaskDetail extends ProductionTask {
  is_blocked: boolean;
  blocked_by_dependencies: boolean;
  unmet_dependency_ids: string[];
  depends_on_ids: string[];
  dependent_ids: string[];
  subtask_count: number;
  allowed_transitions: ProductionTaskStatus[];
}

export interface Dependency {
  id: string;
  task_id: string;
  depends_on_id: string;
  type: string;
  note: string | null;
  depends_on_title: string | null;
  depends_on_status: ProductionTaskStatus | null;
  satisfied: boolean | null;
}

export interface ProductionActivity {
  id: string;
  created_at: string;
  task_id: string | null;
  actor_id: string | null;
  type: string;
  field: string | null;
  from_status: ProductionTaskStatus | null;
  to_status: ProductionTaskStatus | null;
  summary: string | null;
  detail: string | null;
}

export interface Milestone {
  id: string;
  title: string;
  description: string | null;
  work_id: string | null;
  division: StudioDivision | null;
  status: string;
  sequence_order: number;
  target_date: string | null;
  reached_date: string | null;
  task_count: number | null;
}

export interface ApprovalRequest {
  id: string;
  created_at: string;
  requested_by_id: string | null;
  requested_by_name: string | null;
  approver_id: string | null;
  approver_name: string | null;
  task_id: string | null;
  target_type: string | null;
  target_id: string | null;
  title: string | null;
  description: string | null;
  status: ApprovalStatus;
  decision: string | null;
  comments: string | null;
  decided_at: string | null;
}

export interface ProductionTemplate {
  key: string;
  name: string;
  division: StudioDivision;
  description: string;
  milestones: { key: string; title: string; offset_days: number }[];
  tasks: {
    key: string;
    title: string;
    track: ProductionTrack;
    task_type: ProductionTaskType;
    priority: ProductionPriority;
    offset_days: number;
    milestone: string | null;
    depends_on: string[];
    acceptance_criteria: string | null;
  }[];
}
