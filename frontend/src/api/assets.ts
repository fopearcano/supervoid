import { apiBlobUrl, apiFetch, apiPatchJson, apiPostJson } from './client';
import type { Page } from '@/types/manuscript';
import type {
  Asset,
  AssetApprovalStatus,
  AssetDetail,
  AssetLink,
  AssetLinkTargetType,
  AssetType,
  AssetVersion,
  AssetVisibility,
  Licence,
  LicenceType,
  LicenceWarning,
  Provenance,
  ProvenanceCompleteness,
  ProvenanceKind,
} from '@/types/assets';

function toQuery(params: Record<string, unknown>): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    usp.set(key, String(value));
  }
  const s = usp.toString();
  return s ? `?${s}` : '';
}

export interface AssetFilters {
  q?: string;
  asset_type?: AssetType;
  work_id?: string;
  story_world_id?: string;
  visibility?: AssetVisibility;
  tag?: string;
}

export const fetchAssets = (filters: AssetFilters = {}) =>
  apiFetch<Page<Asset>>(`/assets${toQuery({ limit: 200, ...filters })}`);

export const fetchAsset = (id: string) => apiFetch<AssetDetail>(`/assets/${id}`);

export interface AssetInput {
  title: string;
  asset_type?: AssetType;
  work_id?: string | null;
  story_world_id?: string | null;
  visibility?: AssetVisibility;
  tags?: string[];
  description?: string | null;
}

export const createAsset = (body: AssetInput) =>
  apiPostJson<AssetDetail>('/assets', body);

export const patchAsset = (id: string, body: Partial<AssetInput>) =>
  apiPatchJson<AssetDetail>(`/assets/${id}`, body);

export const deleteAsset = (id: string) =>
  apiFetch<void>(`/assets/${id}`, { method: 'DELETE' });

// --- versions --------------------------------------------------------------

export const fetchVersions = (assetId: string) =>
  apiFetch<AssetVersion[]>(`/assets/${assetId}/versions`);

export const uploadVersion = (
  assetId: string,
  file: File,
  makeCurrent: boolean,
): Promise<AssetVersion> => {
  const form = new FormData();
  form.append('file', file);
  form.append('make_current', makeCurrent ? 'true' : 'false');
  return apiFetch<AssetVersion>(`/assets/${assetId}/versions/upload`, {
    method: 'POST',
    body: form,
  });
};

export const promoteVersion = (assetId: string, versionId: string) =>
  apiPostJson<AssetDetail>(`/assets/${assetId}/versions/${versionId}/promote`, {});

export const rollbackVersion = (assetId: string, versionId: string) =>
  apiPostJson<AssetDetail>(`/assets/${assetId}/versions/${versionId}/rollback`, {});

export const setVersionApproval = (
  assetId: string,
  versionId: string,
  approval_status: AssetApprovalStatus,
) =>
  apiPostJson<AssetVersion>(`/assets/${assetId}/versions/${versionId}/approve`, {
    approval_status,
  });

export const versionDownloadUrl = (assetId: string, versionId: string) =>
  apiBlobUrl(`/assets/${assetId}/versions/${versionId}/download`);

export const versionPreviewUrl = (assetId: string, versionId: string) =>
  apiBlobUrl(`/assets/${assetId}/versions/${versionId}/preview`);

// --- provenance ------------------------------------------------------------

export const fetchProvenance = (assetId: string, versionId: string) =>
  apiFetch<Provenance | null>(
    `/assets/${assetId}/versions/${versionId}/provenance`,
  );

export interface ProvenanceInput {
  kind: ProvenanceKind;
  provider?: string | null;
  base_model?: string | null;
  prompt?: string | null;
  negative_prompt?: string | null;
  seed?: number | null;
  human_modifications?: string | null;
  generation_date?: string | null;
  responsible_user_id?: string | null;
}

export const saveProvenance = (
  assetId: string,
  versionId: string,
  body: ProvenanceInput,
) =>
  apiFetch<Provenance>(`/assets/${assetId}/versions/${versionId}/provenance`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

export const fetchProvenanceCompleteness = (assetId: string, versionId: string) =>
  apiFetch<ProvenanceCompleteness>(
    `/assets/${assetId}/versions/${versionId}/provenance/completeness`,
  );

// --- licences --------------------------------------------------------------

export const fetchLicences = (assetId: string) =>
  apiFetch<Licence[]>(`/assets/${assetId}/licences`);

export interface LicenceInput {
  licence_type: LicenceType;
  rights_holder?: string | null;
  source?: string | null;
  territory?: string | null;
  permitted_uses?: string | null;
  expiration_date?: string | null;
}

export const createLicence = (assetId: string, body: LicenceInput) =>
  apiPostJson<Licence>(`/assets/${assetId}/licences`, body);

export const fetchLicenceWarnings = () =>
  apiFetch<LicenceWarning[]>('/assets/licence-warnings');

// --- links -----------------------------------------------------------------

export const fetchLinks = (assetId: string) =>
  apiFetch<AssetLink[]>(`/assets/${assetId}/links`);

export const addLink = (
  assetId: string,
  body: { target_type: AssetLinkTargetType; target_id: string; role?: string },
) => apiPostJson<AssetLink>(`/assets/${assetId}/links`, body);
