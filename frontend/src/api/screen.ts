import { apiBlobUrl, apiFetch, apiPatchJson, apiPostJson } from './client';
import type { Page } from '@/types/manuscript';
import type { AdaptationDossier } from '@/types/transmedia';
import type {
  Breakdown,
  CameraAngle,
  CameraFraming,
  References,
  Scene,
  SceneCharacter,
  SceneDetail,
  SceneEnvironment,
  SceneTimeOfDay,
  ScreenFormat,
  ScreenProject,
  ScreenProjectStatus,
  ScreenSequence,
  ScreenStatus,
  ScreenUnit,
  Shot,
  ShotApproval,
  ShotMovement,
  StoryboardRef,
} from '@/types/screen';

// --- promotion + project creation ------------------------------------------

export interface PromoteInput {
  source_work_id: string;
  target_medium?: string;
  logline?: string | null;
  status?: string;
}

export const promoteToDossier = (body: PromoteInput) =>
  apiPostJson<AdaptationDossier>('/screen/dossiers/promote', body);

export const createProjectFromDossier = (dossierId: string, format: ScreenFormat, title?: string) =>
  apiPostJson<ScreenProject>(`/screen/projects/from-dossier/${dossierId}`, { format, title });

// --- projects --------------------------------------------------------------

export const fetchProjects = () =>
  apiFetch<Page<ScreenProject>>('/screen/projects?limit=200');

export const fetchProject = (id: string) =>
  apiFetch<ScreenProject>(`/screen/projects/${id}`);

export const patchProject = (id: string, body: Partial<{ status: ScreenProjectStatus; synopsis: string | null }>) =>
  apiPatchJson<ScreenProject>(`/screen/projects/${id}`, body);

// --- units / sequences / scenes / shots ------------------------------------

export const fetchUnits = (projectId: string) =>
  apiFetch<ScreenUnit[]>(`/screen/projects/${projectId}/units`);

export const fetchSequences = (unitId: string) =>
  apiFetch<ScreenSequence[]>(`/screen/units/${unitId}/sequences`);

export const createSequence = (unitId: string, title?: string) =>
  apiPostJson<ScreenSequence>(`/screen/units/${unitId}/sequences`, { title });

export const fetchScenes = (sequenceId: string) =>
  apiFetch<Scene[]>(`/screen/sequences/${sequenceId}/scenes`);

export interface SceneInput {
  scene_number?: number;
  heading?: string | null;
  location?: string | null;
  environment?: SceneEnvironment;
  time_of_day?: SceneTimeOfDay;
  synopsis?: string | null;
  estimated_duration_seconds?: number | null;
  production_status?: ScreenStatus;
  continuity_notes?: string | null;
}

export const createScene = (sequenceId: string, body: SceneInput) =>
  apiPostJson<SceneDetail>(`/screen/sequences/${sequenceId}/scenes`, body);

export const fetchScene = (sceneId: string) =>
  apiFetch<SceneDetail>(`/screen/scenes/${sceneId}`);

export const patchScene = (sceneId: string, body: SceneInput) =>
  apiPatchJson<SceneDetail>(`/screen/scenes/${sceneId}`, body);

export const addSceneCharacter = (sceneId: string, entity_id: string, role?: string) =>
  apiPostJson<SceneCharacter>(`/screen/scenes/${sceneId}/characters`, { entity_id, role });

export interface ShotInput {
  shot_number?: number;
  framing?: CameraFraming | null;
  camera_angle?: CameraAngle | null;
  movement?: ShotMovement | null;
  lens?: string | null;
  duration_seconds?: number | null;
  blocking?: string | null;
  lighting?: string | null;
  dialogue?: string | null;
  sound?: string | null;
  music?: string | null;
  vfx?: string | null;
  source_storyboard_panel_id?: string | null;
  status?: ScreenStatus;
  approval?: ShotApproval;
}

export const createShot = (sceneId: string, body: ShotInput) =>
  apiPostJson<Shot>(`/screen/scenes/${sceneId}/shots`, body);

export const patchShot = (shotId: string, body: ShotInput) =>
  apiPatchJson<Shot>(`/screen/shots/${shotId}`, body);

export const deleteShot = (shotId: string) =>
  apiFetch<void>(`/screen/shots/${shotId}`, { method: 'DELETE' });

export const mapPanelToShot = (shotId: string, panel_id: string) =>
  apiPostJson<Shot>(`/screen/shots/${shotId}/panels`, { panel_id });

// --- storyboard / shot list / breakdown / references / export --------------

export const fetchStoryboard = (projectId: string) =>
  apiFetch<StoryboardRef[]>(`/screen/projects/${projectId}/storyboard`);

export const fetchShotList = (projectId: string) =>
  apiFetch<Record<string, unknown>[]>(`/screen/projects/${projectId}/shot-list`);

export const fetchBreakdown = (projectId: string) =>
  apiFetch<Breakdown>(`/screen/projects/${projectId}/breakdown`);

export const fetchReferences = (projectId: string) =>
  apiFetch<References>(`/screen/projects/${projectId}/references`);

export const exportJsonUrl = (projectId: string) =>
  apiBlobUrl(`/screen/projects/${projectId}/export?format=json`);

export const exportMarkdownUrl = (projectId: string) =>
  apiBlobUrl(`/screen/projects/${projectId}/export?format=markdown`);
