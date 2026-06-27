import { apiFetch, apiPostJson } from './client';
import type {
  BrainEvent,
  BrainRevision,
  CompilerHealth,
  ProjectBrainState,
  RebuildResult,
  StaleReport,
  StudioBrainState,
} from '@/types/brain';

// --- compiled state --------------------------------------------------------
export const fetchStudioState = () =>
  apiFetch<StudioBrainState | null>('/brain/state/studio');

export const fetchWorkState = (workId: string) =>
  apiFetch<ProjectBrainState | null>(`/brain/works/${workId}/state`);

export const fetchWorldState = (worldId: string) =>
  apiFetch<ProjectBrainState | null>(`/brain/story-worlds/${worldId}/state`);

// --- revisions / events (admin) -------------------------------------------
export const fetchRevisions = (params: { state_type?: string; state_id?: string } = {}) => {
  const usp = new URLSearchParams({ limit: '50' });
  if (params.state_type) usp.set('state_type', params.state_type);
  if (params.state_id) usp.set('state_id', params.state_id);
  return apiFetch<BrainRevision[]>(`/brain/revisions?${usp.toString()}`);
};

export const fetchEvents = (params: { after_sequence?: number; limit?: number } = {}) => {
  const usp = new URLSearchParams({ limit: String(params.limit ?? 50) });
  if (params.after_sequence !== undefined) usp.set('after_sequence', String(params.after_sequence));
  return apiFetch<BrainEvent[]>(`/brain/events?${usp.toString()}`);
};

export const fetchDelta = (a: string, b: string) =>
  apiFetch<{ added: string[]; removed: string[]; changed: string[] }>(
    `/brain/revisions/${a}/delta/${b}`,
  );

// --- compiler health / staleness ------------------------------------------
export const fetchCompilerHealth = () => apiFetch<CompilerHealth>('/brain/health');
export const fetchStale = () => apiFetch<StaleReport>('/brain/stale');

// --- rebuild controls (admin) ---------------------------------------------
export const rebuildStudio = (full = false) =>
  apiPostJson<RebuildResult>('/brain/state/studio/rebuild', { full });

export const rebuildWork = (workId: string, full = false) =>
  apiPostJson<RebuildResult>(`/brain/works/${workId}/state/rebuild`, { full });

export const rebuildWorld = (worldId: string, full = false) =>
  apiPostJson<RebuildResult>(`/brain/story-worlds/${worldId}/state/rebuild`, { full });

// --- outbox backlog controls ----------------------------------------------
export const processOutbox = () => apiPostJson<Record<string, number>>('/brain/outbox/process', {});
export const reconcileOutbox = () => apiPostJson<Record<string, unknown>>('/brain/outbox/reconcile', {});

// --- native in-app chat (talks to the Brain Gateway as the session user) ---
export interface BrainCitation {
  ref: string;
  label: string;
}

export interface BrainProposalRef {
  tool: string;
  proposal_id?: string | null;
  status?: string | null;
}

export interface BrainChatTurn {
  conversation_id: string;
  content: string;
  model: string;
  state_version: number | null;
  citations: BrainCitation[];
  tools_used: string[];
  proposals: BrainProposalRef[];
  usage: Record<string, number>;
}

export const sendBrainChat = (body: {
  content: string;
  conversation_id?: string | null;
  work_id?: string | null;
  story_world_id?: string | null;
  profile?: string | null;
}) => apiPostJson<BrainChatTurn>('/brain/chat', body);

// --- private navigation: hand-off + status (Prompt 12) ---------------------
export interface BrainHandoff {
  handoff_url: string;
  conversation_id: string | null;
  work_id: string | null;
  story_world_id: string | null;
  label: string | null;
  expires_at: string;
}

export interface BrainStatus {
  active_project: {
    entity_type?: string;
    label?: string | null;
    work_id?: string | null;
    story_world_id?: string | null;
  } | null;
  state_version: number | null;
  model: { provider?: string; model?: string; gateway_model?: string };
  compiler: {
    head_sequence?: number | null;
    studio_stale?: boolean | null;
    studio_version?: number | null;
    stale_projects?: number | null;
  };
  pending_proposals: number;
  brain_url: string;
}

export const requestBrainHandoff = (entityType: string, entityId: string, profile?: string) =>
  apiPostJson<BrainHandoff>('/brain/handoff', {
    entity_type: entityType,
    entity_id: entityId,
    profile,
  });

export const fetchBrainStatus = () => apiFetch<BrainStatus>('/brain/status');

// --- conversation memory: review inbox (Prompt 13) -------------------------
export interface BrainMemoryItem {
  id: string;
  scope: 'studio' | 'project' | 'member' | 'conversation';
  work_id: string | null;
  story_world_id: string | null;
  member_user_id: string | null;
  conversation_id: string | null;
  kind: string;
  content: string;
  structured_data: Record<string, unknown>;
  confidence: number | null;
  topic_key: string | null;
  risk_level: string;
  auto_accepted: boolean;
  verification: 'unverified' | 'verified' | 'rejected' | 'superseded' | 'expired';
  supersedes_id: string | null;
  created_by_id: string | null;
  reviewed_by_id: string | null;
  review_note: string | null;
  created_at: string;
}

export const fetchMemoryInbox = (params: { scope?: string; work_id?: string } = {}) => {
  const usp = new URLSearchParams({ limit: '100' });
  if (params.scope) usp.set('scope', params.scope);
  if (params.work_id) usp.set('work_id', params.work_id);
  return apiFetch<BrainMemoryItem[]>(`/brain/memory/inbox?${usp.toString()}`);
};

export const acceptMemory = (id: string, note?: string) =>
  apiPostJson<BrainMemoryItem>(`/brain/memory/${id}/accept`, { note });

export const rejectMemory = (id: string, note?: string) =>
  apiPostJson<BrainMemoryItem>(`/brain/memory/${id}/reject`, { note });

export const editMemory = (id: string, content: string, note?: string) =>
  apiPostJson<BrainMemoryItem>(`/brain/memory/${id}/edit`, { content, note });

export const supersedeMemory = (id: string, content: string, note?: string) =>
  apiPostJson<BrainMemoryItem>(`/brain/memory/${id}/supersede`, { content, note });

export const mergeMemory = (id: string, sourceIds: string[], content?: string) =>
  apiPostJson<BrainMemoryItem>(`/brain/memory/${id}/merge`, { source_ids: sourceIds, content });

export const expireMemory = (id: string, note?: string) =>
  apiPostJson<BrainMemoryItem>(`/brain/memory/${id}/expire`, { note });
