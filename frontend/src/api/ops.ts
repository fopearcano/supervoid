import { apiFetch, apiPostJson } from './client';

export interface OpsHealth {
  overall: string;
  components: Record<string, string>;
}

// The status payload is a deep nested snapshot; typed loosely on purpose.
export type OpsStatus = Record<string, any>;

export const fetchOpsStatus = () => apiFetch<OpsStatus>('/brain/ops/status');
export const fetchOpsHealth = () => apiFetch<OpsHealth>('/brain/ops/health');

export const setModelRequests = (enabled: boolean) =>
  apiPostJson<OpsStatus>('/brain/ops/controls/model-requests', { enabled });
export const setDrain = (draining: boolean) =>
  apiPostJson<OpsStatus>('/brain/ops/controls/drain', { draining });
export const setMcp = (enabled: boolean) =>
  apiPostJson<OpsStatus>('/brain/ops/controls/mcp', { enabled });
export const replayEvents = () =>
  apiPostJson<{ requeued: number }>('/brain/ops/events/replay', {});
export const rebuildProject = (workId: string) =>
  apiPostJson<OpsStatus>(`/brain/ops/projects/${workId}/rebuild`, {});
export const markProjectCold = (workId: string) =>
  apiPostJson<OpsStatus>(`/brain/ops/projects/${workId}/cold`, {});
export const prewarmProject = (workId: string) =>
  apiPostJson<OpsStatus>(`/brain/ops/projects/${workId}/prewarm`, {});
export const revokeAnyToken = (tokenId: string) =>
  apiPostJson<OpsStatus>(`/brain/ops/tokens/${tokenId}/revoke`, {});
