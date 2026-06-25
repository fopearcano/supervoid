import { apiFetch, apiPostJson } from './client';
import type { Page } from '@/types/manuscript';
import type {
  AdapterHealth,
  ConfigStatus,
  IntegrationAdapter,
  IntegrationLink,
  IntegrationPoint,
  IntegrationRun,
} from '@/types/integrations';

export const fetchAdapters = () =>
  apiFetch<IntegrationAdapter[]>('/integrations/adapters');

export const fetchPoints = () =>
  apiFetch<Page<IntegrationPoint>>('/integrations/points?limit=100');

export const fetchPointHealth = (id: string) =>
  apiFetch<AdapterHealth>(`/integrations/points/${id}/health`);

export const fetchPointConfig = (id: string) =>
  apiFetch<ConfigStatus>(`/integrations/points/${id}/config`);

export const requestOperation = (
  pointId: string,
  operation: string,
  payload: Record<string, unknown>,
  dryRun: boolean,
) =>
  apiPostJson<IntegrationRun>(`/integrations/points/${pointId}/operations`, {
    operation,
    payload,
    dry_run: dryRun,
  });

export const fetchRuns = (
  params: { point_id?: string; status?: string; adapter_key?: string } = {},
) => {
  const usp = new URLSearchParams({ limit: '100' });
  if (params.point_id) usp.set('point_id', params.point_id);
  if (params.status) usp.set('status', params.status);
  if (params.adapter_key) usp.set('adapter_key', params.adapter_key);
  return apiFetch<Page<IntegrationRun>>(`/integrations/runs?${usp.toString()}`);
};

export const fetchRun = (id: string) =>
  apiFetch<IntegrationRun>(`/integrations/runs/${id}`);

export const approveRun = (id: string) =>
  apiPostJson<IntegrationRun>(`/integrations/runs/${id}/approve`, {});

export const rejectRun = (id: string, reason?: string) =>
  apiPostJson<IntegrationRun>(`/integrations/runs/${id}/reject`, { reason });

export const executeRun = (id: string) =>
  apiPostJson<IntegrationRun>(`/integrations/runs/${id}/execute`, {});

export const fetchLinks = (targetId?: string) => {
  const usp = new URLSearchParams({ limit: '100' });
  if (targetId) usp.set('target_id', targetId);
  return apiFetch<Page<IntegrationLink>>(`/integrations/links?${usp.toString()}`);
};
