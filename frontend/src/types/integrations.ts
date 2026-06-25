// Types for the operational integration hub.

export type IntegrationRunStatus =
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled';

export type IntegrationHealthStatus =
  | 'healthy'
  | 'degraded'
  | 'unreachable'
  | 'not_configured'
  | 'disabled'
  | 'unknown';

export type IntegrationLinkKind =
  | 'commit'
  | 'issue'
  | 'pull_request'
  | 'branch'
  | 'release'
  | 'other';

export function iLabel(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export interface AdapterOperation {
  key: string;
  name: string;
  summary: string;
  direction: string;
  mutating: boolean;
  external: boolean;
  touches_network: boolean;
  requires_approval: boolean;
  admin_gated: boolean;
  read_only: boolean;
  risk: string;
}

export interface IntegrationAdapter {
  key: string;
  kind: string;
  name: string;
  description: string;
  required_config: string[];
  credential_names: string[];
  operations: AdapterOperation[];
}

export interface IntegrationPoint {
  id: string;
  created_at: string;
  updated_at: string;
  name: string;
  type: string;
  status: string;
  endpoint: string | null;
  notes: string | null;
  adapter_key: string | null;
  enabled: boolean;
  config: Record<string, unknown>;
}

export interface AdapterHealth {
  status: IntegrationHealthStatus;
  detail: string;
  configured: boolean;
  checked_live: boolean;
  credentials: Record<string, boolean>;
  missing_config: string[];
}

export interface ConfigStatus {
  adapter_key: string | null;
  enabled: boolean;
  config: Record<string, unknown>;
  credentials: Record<string, boolean>;
  required_config: string[];
  missing_config: string[];
}

export interface IntegrationRun {
  id: string;
  created_at: string;
  updated_at: string;
  integration_point_id: string;
  adapter_key: string;
  operation: string;
  direction: string;
  status: IntegrationRunStatus;
  dry_run: boolean;
  requires_approval: boolean;
  is_external: boolean;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  error: string | null;
  requested_by_id: string | null;
  requested_by_name: string | null;
  approved_by_id: string | null;
  approved_at: string | null;
  rejected_by_id: string | null;
  rejected_at: string | null;
  approval_proposal_id: string | null;
  correlation_id: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface IntegrationLink {
  id: string;
  created_at: string;
  updated_at: string;
  integration_point_id: string;
  external_kind: IntegrationLinkKind;
  external_ref: string;
  external_url: string | null;
  title: string | null;
  target_type: string;
  target_id: string;
  extra: Record<string, unknown>;
}
