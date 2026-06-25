import { apiFetch, apiPatchJson, apiPostJson } from './client';
import type { Page } from '@/types/manuscript';
import type {
  ApprovalAdmin,
  ChapterAdmin,
  MediaAdmin,
  PageAdmin,
  PublicationEventAdmin,
  PublishedStatus,
  PublishedWorkAdmin,
  ValidationResult,
  VolumeAdmin,
} from '@/types/curation';

// --- works -----------------------------------------------------------------

export const fetchPublishedWorks = () =>
  apiFetch<Page<PublishedWorkAdmin>>('/curation/works?limit=100');
export const fetchPublishedWork = (id: string) =>
  apiFetch<PublishedWorkAdmin>(`/curation/works/${id}`);
export const createPublishedWork = (payload: Record<string, unknown>) =>
  apiPostJson<PublishedWorkAdmin>('/curation/works', payload);
export const createFromWork = (sourceWorkId: string) =>
  apiPostJson<PublishedWorkAdmin>('/curation/works/from-work', { source_work_id: sourceWorkId });
export const updatePublishedWork = (id: string, payload: Record<string, unknown>) =>
  apiPatchJson<PublishedWorkAdmin>(`/curation/works/${id}`, payload);

// --- lifecycle -------------------------------------------------------------

export const validateWork = (id: string) =>
  apiFetch<ValidationResult>(`/curation/works/${id}/validate`);
export const fetchEvents = (id: string) =>
  apiFetch<Page<PublicationEventAdmin>>(
    `/curation/works/${id}/events?limit=100`,
  ).then((p) => p.items);
export const fetchApprovals = (id: string) =>
  apiFetch<Page<ApprovalAdmin>>(
    `/curation/works/${id}/approvals?limit=100`,
  ).then((p) => p.items);
export const requestApproval = (id: string) =>
  apiPostJson<ApprovalAdmin>(`/curation/works/${id}/request-approval`, {});
export const decideApproval = (approvalId: string, approve: boolean) =>
  apiPostJson<ApprovalAdmin>(
    `/curation/approvals/${approvalId}/${approve ? 'approve' : 'reject'}`,
    {},
  );
export const publishWork = (id: string) =>
  apiPostJson<PublishedWorkAdmin>(`/curation/works/${id}/publish`, {});
export const unpublishWork = (id: string) =>
  apiPostJson<PublishedWorkAdmin>(`/curation/works/${id}/unpublish`, {});
export const setVisibility = (id: string, status: PublishedStatus) =>
  apiPostJson<PublishedWorkAdmin>(`/curation/works/${id}/visibility`, { status });
export const scheduleWork = (id: string, publication_date: string) =>
  apiPostJson<PublishedWorkAdmin>(`/curation/works/${id}/schedule`, { publication_date });

// --- structure -------------------------------------------------------------

export const fetchVolumes = (workId: string) =>
  apiFetch<VolumeAdmin[]>(`/curation/works/${workId}/volumes`);
export const createVolume = (workId: string, payload: Record<string, unknown>) =>
  apiPostJson<VolumeAdmin>(`/curation/works/${workId}/volumes`, payload);
export const fetchChapters = (volumeId: string) =>
  apiFetch<ChapterAdmin[]>(`/curation/volumes/${volumeId}/chapters`);
export const createChapter = (volumeId: string, payload: Record<string, unknown>) =>
  apiPostJson<ChapterAdmin>(`/curation/volumes/${volumeId}/chapters`, payload);
export const fetchCurationPages = (chapterId: string) =>
  apiFetch<PageAdmin[]>(`/curation/chapters/${chapterId}/pages`);
export const createCurationPage = (chapterId: string, payload: Record<string, unknown>) =>
  apiPostJson<PageAdmin>(`/curation/chapters/${chapterId}/pages`, payload);

// --- media -----------------------------------------------------------------

export const fetchPublicMedia = () =>
  apiFetch<Page<MediaAdmin>>('/curation/media?limit=200').then((p) => p.items);
export const createPublicMedia = (payload: Record<string, unknown>) =>
  apiPostJson<MediaAdmin>('/curation/media', payload);

// --- hand-off --------------------------------------------------------------

export const handoffPage = (payload: Record<string, unknown>) =>
  apiPostJson<PageAdmin>('/curation/handoff/page', payload);
