import { apiFetch } from './client';
import type {
  AgentInbox,
  AssetHealth,
  BusinessAlerts,
  DivisionView,
  MyWork,
  StudioOverview,
  WorkCommand,
} from '@/types/command';

export const fetchOverview = () =>
  apiFetch<StudioOverview>('/command-centre/overview');
export const fetchMyWork = () => apiFetch<MyWork>('/command-centre/my-work');
export const fetchAgentInbox = () =>
  apiFetch<AgentInbox>('/command-centre/agent-inbox');
export const fetchAssetHealth = () =>
  apiFetch<AssetHealth>('/command-centre/asset-health');
export const fetchBusinessAlerts = () =>
  apiFetch<BusinessAlerts>('/command-centre/business-alerts');
export const fetchDivisions = () =>
  apiFetch<DivisionView[]>('/command-centre/divisions');
export const fetchWorkCommand = (workId: string) =>
  apiFetch<WorkCommand>(`/command-centre/works/${workId}/command`);
