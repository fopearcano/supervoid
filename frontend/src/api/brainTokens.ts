import { apiFetch, apiPostJson } from './client';

// Mirror of backend app/schemas/brain_token.py. The plaintext `secret` is only
// ever present on create/rotate responses — never on list/meta.
export interface ProjectRestriction {
  work_id?: string | null;
  story_world_id?: string | null;
}

export interface BrainTokenMeta {
  id: string;
  name: string;
  token_prefix: string;
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  project_restrictions: ProjectRestriction[];
}

export interface BrainTokenSecret {
  token: BrainTokenMeta;
  secret: string;
}

export interface BrainTokenCreate {
  name: string;
  project_restrictions?: ProjectRestriction[];
  expires_in_days?: number | null;
}

export const listBrainTokens = () =>
  apiFetch<BrainTokenMeta[]>('/brain-tokens');

export const createBrainToken = (body: BrainTokenCreate) =>
  apiPostJson<BrainTokenSecret>('/brain-tokens', body);

export const rotateBrainToken = (id: string) =>
  apiPostJson<BrainTokenSecret>(`/brain-tokens/${id}/rotate`, {});

export const revokeBrainToken = (id: string) =>
  apiFetch<void>(`/brain-tokens/${id}`, { method: 'DELETE' });
