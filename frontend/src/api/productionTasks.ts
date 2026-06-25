import { apiFetch, apiPatchJson, apiPostJson } from './client';
import type { Page } from '@/types/manuscript';
import type {
  ApprovalRequest,
  Dependency,
  Milestone,
  ProductionActivity,
  ProductionPriority,
  ProductionTask,
  ProductionTaskDetail,
  ProductionTaskStatus,
  ProductionTaskType,
  ProductionTemplate,
  ProductionTrack,
} from '@/types/productionTasks';

function toQuery(params: Record<string, unknown>): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    usp.set(key, String(value));
  }
  const s = usp.toString();
  return s ? `?${s}` : '';
}

export interface TaskFilters {
  work_id?: string;
  milestone_id?: string;
  assignee_id?: string;
  track?: ProductionTrack;
  task_type?: ProductionTaskType;
  priority?: ProductionPriority;
  status?: ProductionTaskStatus;
  parent_id?: string;
  top_level?: boolean;
  q?: string;
}

export const fetchTasks = (filters: TaskFilters = {}) =>
  apiFetch<Page<ProductionTask>>(
    `/production-tasks${toQuery({ limit: 500, ...filters })}`,
  );

export const fetchTask = (id: string) =>
  apiFetch<ProductionTaskDetail>(`/production-tasks/${id}`);

export interface TaskInput {
  title: string;
  work_id: string;
  description?: string | null;
  track?: ProductionTrack | null;
  task_type?: ProductionTaskType;
  priority?: ProductionPriority;
  assignee_id?: string | null;
  milestone_id?: string | null;
  parent_id?: string | null;
  due_date?: string | null;
  start_date?: string | null;
  estimated_effort?: number | null;
  acceptance_criteria?: string | null;
}

export const createTask = (body: TaskInput) =>
  apiPostJson<ProductionTaskDetail>('/production-tasks', body);

export const patchTask = (id: string, body: Partial<TaskInput>) =>
  apiPatchJson<ProductionTaskDetail>(`/production-tasks/${id}`, body);

export const transitionTask = (
  id: string,
  to_status: ProductionTaskStatus,
  note?: string,
) =>
  apiPostJson<ProductionTaskDetail>(`/production-tasks/${id}/transition`, {
    to_status,
    note,
  });

export const fetchSubtasks = (id: string) =>
  apiFetch<ProductionTask[]>(`/production-tasks/${id}/subtasks`);

export const fetchTaskActivity = (id: string) =>
  apiFetch<ProductionActivity[]>(`/production-tasks/${id}/activity`);

export const fetchDependencies = (id: string) =>
  apiFetch<Dependency[]>(`/production-tasks/${id}/dependencies`);

export const addDependency = (id: string, depends_on_id: string) =>
  apiPostJson<Dependency>(`/production-tasks/${id}/dependencies`, { depends_on_id });

export const removeDependency = (id: string, dependencyId: string) =>
  apiFetch<void>(`/production-tasks/${id}/dependencies/${dependencyId}`, {
    method: 'DELETE',
  });

export const fetchMyAssignments = () =>
  apiFetch<Page<ProductionTask>>('/production-tasks/my-assignments?limit=200');

export const fetchOverdue = () =>
  apiFetch<Page<ProductionTask>>('/production-tasks/overdue?limit=200');

export const fetchBlocked = (work_id?: string) =>
  apiFetch<ProductionTaskDetail[]>(
    `/production-tasks/blocked${toQuery({ work_id })}`,
  );

export const fetchAwaitingApproval = () =>
  apiFetch<ApprovalRequest[]>('/production-tasks/awaiting-approval');

export const requestApproval = (
  taskId: string,
  approver_id: string,
  title?: string,
) =>
  apiPostJson<ApprovalRequest>(`/production-tasks/${taskId}/approvals`, {
    approver_id,
    title,
  });

export const fetchTaskApprovals = (taskId: string) =>
  apiFetch<ApprovalRequest[]>(`/production-tasks/${taskId}/approvals`);

export const decideApproval = (
  approvalId: string,
  decision: 'approved' | 'rejected' | 'changes_requested',
  comments?: string,
) =>
  apiPostJson<ApprovalRequest>(`/approvals/${approvalId}/decide`, {
    decision,
    comments,
  });

// --- Milestones ------------------------------------------------------------

export const fetchMilestones = (work_id?: string) =>
  apiFetch<Page<Milestone>>(`/milestones${toQuery({ work_id, limit: 200 })}`);

export const createMilestone = (body: {
  title: string;
  work_id?: string;
  target_date?: string | null;
}) => apiPostJson<Milestone>('/milestones', body);

// --- Templates -------------------------------------------------------------

export const fetchTemplates = () =>
  apiFetch<ProductionTemplate[]>('/production-templates');

export interface ApplyTemplateResult {
  template_key: string;
  work_id: string;
  milestone_ids: string[];
  task_ids: string[];
  dependency_ids: string[];
}

export const applyTemplate = (workId: string, template_key: string) =>
  apiPostJson<ApplyTemplateResult>(`/works/${workId}/production-template`, {
    template_key,
  });
