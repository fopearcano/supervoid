import { apiFetch, apiPostJson } from './client';

export type IdentityLinkStatus = 'pending' | 'active' | 'disabled' | 'revoked';

export interface IdentityLink {
  id: string;
  supervoid_user_id: string;
  user_email: string | null;
  user_full_name: string | null;
  librechat_user_id: string | null;
  librechat_email: string;
  status: IdentityLinkStatus;
  linked_at: string;
  verified_at: string | null;
  disabled_at: string | null;
  note: string | null;
  created_at: string;
}

export interface MyIdentity {
  linked: boolean;
  status?: IdentityLinkStatus;
  librechat_email?: string | null;
  linked_at?: string | null;
  verified_at?: string | null;
}

export interface SecurityEvent {
  id: string;
  created_at: string;
  event_type: string;
  severity: 'info' | 'warning' | 'critical';
  source: string;
  supervoid_user_id: string | null;
  librechat_user_id: string | null;
  email: string | null;
  reason: string | null;
  work_id: string | null;
  token_id: string | null;
}

export interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
}

export interface CreateIdentityLink {
  supervoid_user_id: string;
  librechat_email: string;
  librechat_user_id?: string | null;
  note?: string | null;
  verify?: boolean;
}

export const listIdentityLinks = () => apiFetch<IdentityLink[]>('/identity-links');

export const createIdentityLink = (body: CreateIdentityLink) =>
  apiPostJson<IdentityLink>('/identity-links', body);

export const verifyIdentityLink = (id: string) =>
  apiPostJson<IdentityLink>(`/identity-links/${id}/verify`, {});

export const disableIdentityLink = (id: string, note?: string) =>
  apiPostJson<IdentityLink>(`/identity-links/${id}/disable`, { note });

export const fetchMyIdentity = () => apiFetch<MyIdentity>('/identity-links/me');

export const listSecurityEvents = (params: { severity?: string; source?: string } = {}) => {
  const usp = new URLSearchParams({ limit: '100' });
  if (params.severity) usp.set('severity', params.severity);
  if (params.source) usp.set('source', params.source);
  return apiFetch<SecurityEvent[]>(`/security-events?${usp.toString()}`);
};

export const listAdminUsers = () =>
  apiFetch<{ items: AdminUser[] }>('/users?limit=200');

/** Admin user list, unwrapped to an array (empty on failure). */
export const fetchAdminUsersSafe = async (): Promise<AdminUser[]> => {
  const page = await listAdminUsers();
  return page.items ?? [];
};
