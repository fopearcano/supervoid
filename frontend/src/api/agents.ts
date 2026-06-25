import { apiFetch, apiPostJson } from './client';
import type { Page } from '@/types/manuscript';
import type {
  AgentDefinition,
  AgentFinding,
  AgentProposal,
  AgentRun,
  AgentRunDetail,
  AgentTool,
  FindingSeverity,
  ProposalStatus,
} from '@/types/agents';

export const fetchAgents = () => apiFetch<AgentDefinition[]>('/agents');
export const fetchTools = () => apiFetch<AgentTool[]>('/agents/tools');

export const runAgent = (key: string, target_type: string, target_id: string) =>
  apiPostJson<AgentRunDetail>(`/agents/${key}/run`, { target_type, target_id });

export const fetchRuns = (params: { agent_key?: string; status?: string } = {}) => {
  const usp = new URLSearchParams({ limit: '100' });
  if (params.agent_key) usp.set('agent_key', params.agent_key);
  if (params.status) usp.set('status', params.status);
  return apiFetch<Page<AgentRun>>(`/agent-runs?${usp.toString()}`);
};

export const fetchRun = (id: string) => apiFetch<AgentRunDetail>(`/agent-runs/${id}`);

export const retryRun = (id: string) =>
  apiPostJson<AgentRunDetail>(`/agent-runs/${id}/retry`, {});

export const fetchFindings = (params: { resolved?: boolean; severity?: FindingSeverity } = {}) => {
  const usp = new URLSearchParams({ limit: '100' });
  if (params.resolved !== undefined) usp.set('resolved', String(params.resolved));
  if (params.severity) usp.set('severity', params.severity);
  return apiFetch<Page<AgentFinding>>(`/agent-findings?${usp.toString()}`);
};

export const resolveFinding = (id: string) =>
  apiPostJson<AgentFinding>(`/agent-findings/${id}/resolve`, {});

export const fetchProposals = (status?: ProposalStatus) => {
  const usp = new URLSearchParams({ limit: '100' });
  if (status) usp.set('status', status);
  return apiFetch<Page<AgentProposal>>(`/agent-proposals?${usp.toString()}`);
};

export const approveProposal = (id: string) =>
  apiPostJson<AgentProposal>(`/agent-proposals/${id}/approve`, {});

export const rejectProposal = (id: string, reason?: string) =>
  apiPostJson<AgentProposal>(`/agent-proposals/${id}/reject`, { reason });

export const executeProposal = (id: string) =>
  apiPostJson<AgentProposal>(`/agent-proposals/${id}/execute`, {});
