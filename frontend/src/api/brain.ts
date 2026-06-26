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
