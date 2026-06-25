// Types for the supervised studio-agent framework (Agent Centre).

export type AgentMutability = 'read_only' | 'propose_only';
export type AgentRunStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled';
export type FindingSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';
export type AgentRiskLevel = 'low' | 'medium' | 'high' | 'critical';
export type ProposalStatus = 'pending' | 'approved' | 'rejected' | 'executed' | 'failed' | 'cancelled';
export type AgentToolKind = 'read_only' | 'mutation' | 'external';

export function agLabel(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export interface AgentDefinition {
  key: string;
  name: string;
  description: string;
  supported_entity_types: string[];
  required_permissions: string[];
  allowed_tools: string[];
  mutability: AgentMutability;
  default_provider: string;
  default_model: string | null;
  enabled: boolean;
}

export interface AgentTool {
  key: string;
  name: string;
  description: string;
  kind: AgentToolKind;
  risk_level: AgentRiskLevel;
  required_permissions: string[];
  always_requires_approval: boolean;
}

export interface AgentFinding {
  id: string;
  created_at: string;
  run_id: string;
  agent_key: string;
  severity: FindingSeverity;
  category: string | null;
  target_type: string | null;
  target_id: string | null;
  message: string;
  evidence: Record<string, unknown>;
  confidence: number | null;
  resolved: boolean;
  resolved_by_id: string | null;
  resolved_at: string | null;
}

export interface AgentProposal {
  id: string;
  created_at: string;
  run_id: string;
  agent_key: string;
  tool_key: string;
  action_type: string;
  target_type: string | null;
  target_id: string | null;
  payload: Record<string, unknown>;
  reason: string | null;
  risk_level: AgentRiskLevel;
  requires_approval: boolean;
  status: ProposalStatus;
  approved_by_id: string | null;
  rejected_by_id: string | null;
  execution_result: Record<string, unknown>;
  error: string | null;
}

export interface AgentRun {
  id: string;
  created_at: string;
  agent_key: string;
  requested_by_id: string | null;
  target_type: string | null;
  target_id: string | null;
  provider: string;
  model: string | null;
  status: AgentRunStatus;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  cost_usd: number | null;
  correlation_id: string | null;
  retry_of_id: string | null;
  finding_count: number;
  proposal_count: number;
}

export interface AgentRunDetail extends AgentRun {
  input_snapshot: Record<string, unknown>;
  result: Record<string, unknown>;
  findings: AgentFinding[];
  proposals: AgentProposal[];
}

export interface PromptTemplate {
  id: string;
  key: string;
  name: string;
  description: string | null;
  current_version: number;
  enabled: boolean;
}
