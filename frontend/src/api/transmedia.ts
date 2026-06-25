import { apiFetch, apiPatchJson, apiPostJson } from './client';
import type { Page } from '@/types/manuscript';
import type {
  AdaptationDossier,
  AdaptationStatus,
  CanonState,
  Medium,
  StorySeries,
  StorySeriesStatus,
  StoryWorld,
  StoryWorldStatus,
  StudioDivision,
  TransmediaWork,
  WorkTransmediaOverview,
} from '@/types/transmedia';

function toQuery(params: Record<string, unknown>): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    usp.set(key, String(value));
  }
  const s = usp.toString();
  return s ? `?${s}` : '';
}

// --- Story worlds ----------------------------------------------------------

export const fetchStoryWorlds = (params: { status?: StoryWorldStatus } = {}) =>
  apiFetch<Page<StoryWorld>>(`/story-worlds${toQuery({ limit: 200, ...params })}`);

export const fetchStoryWorld = (id: string) =>
  apiFetch<StoryWorld>(`/story-worlds/${id}`);

export type StoryWorldInput = Partial<{
  name: string;
  slug: string | null;
  description: string | null;
  canon_summary: string | null;
  status: StoryWorldStatus;
  visual_identity_notes: string | null;
  default_language: string;
  owner_id: string | null;
  parent_id: string | null;
}>;

export const createStoryWorld = (body: StoryWorldInput & { name: string }) =>
  apiPostJson<StoryWorld>('/story-worlds', body);

export const patchStoryWorld = (id: string, body: StoryWorldInput) =>
  apiPatchJson<StoryWorld>(`/story-worlds/${id}`, body);

export const deleteStoryWorld = (id: string) =>
  apiFetch<void>(`/story-worlds/${id}`, { method: 'DELETE' });

// --- Series ----------------------------------------------------------------

export const fetchStorySeries = (story_world_id?: string) =>
  apiFetch<Page<StorySeries>>(
    `/story-series${toQuery({ story_world_id, limit: 200 })}`,
  );

export type StorySeriesInput = Partial<{
  story_world_id: string;
  title: string;
  description: string | null;
  sequence_order: number;
  status: StorySeriesStatus;
}>;

export const createStorySeries = (
  body: StorySeriesInput & { story_world_id: string; title: string },
) => apiPostJson<StorySeries>('/story-series', body);

export const patchStorySeries = (id: string, body: StorySeriesInput) =>
  apiPatchJson<StorySeries>(`/story-series/${id}`, body);

export const deleteStorySeries = (id: string) =>
  apiFetch<void>(`/story-series/${id}`, { method: 'DELETE' });

// --- Works (transmedia-aware) ---------------------------------------------

export const fetchWorks = (
  params: {
    story_world_id?: string;
    story_series_id?: string;
    primary_division?: StudioDivision;
    primary_medium?: Medium;
    canon_status?: CanonState;
  } = {},
) => apiFetch<Page<TransmediaWork>>(`/works${toQuery({ limit: 200, ...params })}`);

export const fetchWorkTransmedia = (id: string) =>
  apiFetch<WorkTransmediaOverview>(`/works/${id}/transmedia`);

// --- Adaptation dossiers ---------------------------------------------------

export const fetchAdaptationDossiers = (
  params: {
    source_work_id?: string;
    status?: AdaptationStatus;
    target_medium?: Medium;
    target_division?: StudioDivision;
  } = {},
) =>
  apiFetch<Page<AdaptationDossier>>(
    `/adaptation-dossiers${toQuery({ limit: 200, ...params })}`,
  );

export type AdaptationDossierInput = Partial<{
  source_work_id: string;
  target_work_id: string | null;
  target_medium: Medium;
  target_division: StudioDivision;
  status: AdaptationStatus;
  logline: string | null;
  format: string | null;
  intended_scope: string | null;
  rights_clearance: string;
  creative_notes: string | null;
  source_revision: string | null;
}>;

export const createAdaptationDossier = (
  body: AdaptationDossierInput & { source_work_id: string; target_medium: Medium },
) => apiPostJson<AdaptationDossier>('/adaptation-dossiers', body);

export const patchAdaptationDossier = (id: string, body: AdaptationDossierInput) =>
  apiPatchJson<AdaptationDossier>(`/adaptation-dossiers/${id}`, body);

export const deleteAdaptationDossier = (id: string) =>
  apiFetch<void>(`/adaptation-dossiers/${id}`, { method: 'DELETE' });
