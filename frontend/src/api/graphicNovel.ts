import { apiFetch, apiPatchJson, apiPostJson } from './client';
import type { Page as PageList } from '@/types/manuscript';
import type {
  CameraAngle,
  CameraFraming,
  CurationHandoff,
  GNProduction,
  GNStatus,
  PageDetail,
  PageSide,
  Page as GNPage,
  Panel,
  PanelApproval,
  Progress,
  Readiness,
  StreamStatus,
  TreeNode,
  ValidationIssue,
} from '@/types/graphicNovel';

export const fetchProductions = () =>
  apiFetch<PageList<GNProduction>>('/graphic-novel-productions?limit=200');

export const fetchProduction = (id: string) =>
  apiFetch<GNProduction>(`/graphic-novel-productions/${id}`);

export const fetchTree = (productionId: string) =>
  apiFetch<TreeNode[]>(`/graphic-novel-productions/${productionId}/tree`);

export const fetchProgress = (productionId: string) =>
  apiFetch<Progress>(`/graphic-novel-productions/${productionId}/progress`);

export const fetchReadiness = (productionId: string) =>
  apiFetch<Readiness>(`/graphic-novel-productions/${productionId}/readiness`);

export const validateProduction = (productionId: string) =>
  apiFetch<ValidationIssue[]>(`/graphic-novel-productions/${productionId}/validate`);

export const recalculate = (productionId: string) =>
  apiPostJson<Progress>(`/graphic-novel-productions/${productionId}/recalculate`, {});

export const curationHandoff = (productionId: string, commit = false) =>
  apiFetch<CurationHandoff>(
    `/graphic-novel-productions/${productionId}/curation-handoff${commit ? '?commit=true' : ''}`,
  );

// --- create nodes ----------------------------------------------------------

export const createVolume = (productionId: string, title?: string) =>
  apiPostJson<{ id: string }>(`/graphic-novel-productions/${productionId}/volumes`, {
    title,
  });

export const createChapter = (volumeId: string, title?: string) =>
  apiPostJson<{ id: string }>(`/gn-volumes/${volumeId}/chapters`, { title });

export const createSequence = (chapterId: string, title?: string) =>
  apiPostJson<{ id: string }>(`/gn-chapters/${chapterId}/sequences`, { title });

export const createPage = (sequenceId: string, page_number: number) =>
  apiPostJson<PageDetail>(`/gn-sequences/${sequenceId}/pages`, { page_number });

// --- pages -----------------------------------------------------------------

export const fetchPage = (pageId: string) =>
  apiFetch<PageDetail>(`/gn-pages/${pageId}`);

export interface PagePatch {
  status?: GNStatus;
  page_side?: PageSide;
  lettering_status?: StreamStatus;
  colour_status?: StreamStatus;
  final_status?: StreamStatus;
  print_width_mm?: number | null;
  print_height_mm?: number | null;
  bleed_mm?: number | null;
  safe_area_mm?: number | null;
  master_asset_id?: string | null;
  script?: string | null;
  visual_brief?: string | null;
  spread_id?: string | null;
}

export const patchPage = (pageId: string, body: PagePatch) =>
  apiPatchJson<PageDetail>(`/gn-pages/${pageId}`, body);

export const duplicatePage = (pageId: string) =>
  apiPostJson<PageDetail>(`/gn-pages/${pageId}/duplicate`, {});

export const validatePage = (pageId: string) =>
  apiFetch<ValidationIssue[]>(`/gn-pages/${pageId}/validate`);

export const reorderPages = (sequenceId: string, ordered_ids: string[]) =>
  apiPostJson<GNPage[]>(`/gn-sequences/${sequenceId}/pages/reorder`, { ordered_ids });

// --- panels ----------------------------------------------------------------

export const createPanel = (pageId: string, panel_number: number) =>
  apiPostJson<Panel>(`/gn-pages/${pageId}/panels`, {
    panel_number,
    x: 0.05,
    y: 0.05,
    width: 0.4,
    height: 0.4,
  });

export interface PanelPatch {
  status?: GNStatus;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  script_beat?: string | null;
  dialogue?: string | null;
  captions?: string | null;
  sound_effects?: string | null;
  camera_framing?: CameraFraming | null;
  camera_angle?: CameraAngle | null;
  lens_metadata?: string | null;
  continuity_notes?: string | null;
  approval_status?: PanelApproval;
}

export const patchPanel = (panelId: string, body: PanelPatch) =>
  apiPatchJson<Panel>(`/gn-panels/${panelId}`, body);

export const deletePanel = (panelId: string) =>
  apiFetch<void>(`/gn-panels/${panelId}`, { method: 'DELETE' });

export const duplicatePanel = (panelId: string) =>
  apiPostJson<Panel>(`/gn-panels/${panelId}/duplicate`, {});

export const reorderPanels = (pageId: string, ordered_ids: string[]) =>
  apiPostJson<Panel[]>(`/gn-pages/${pageId}/panels/reorder`, { ordered_ids });
