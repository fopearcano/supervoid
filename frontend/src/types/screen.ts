// Types for the SUPERVOID Pictures bounded context.

export type ScreenFormat = 'film' | 'short' | 'series' | 'animation';
export type ScreenUnitType = 'episode' | 'reel' | 'act' | 'part';
export type ScreenProjectStatus =
  | 'development' | 'pre_production' | 'production' | 'post_production'
  | 'delivered' | 'on_hold' | 'cancelled';
export type ScreenStatus = 'planned' | 'in_progress' | 'in_review' | 'complete' | 'on_hold';
export type SceneEnvironment = 'int' | 'ext' | 'int_ext';
export type SceneTimeOfDay =
  | 'day' | 'night' | 'dawn' | 'dusk' | 'morning' | 'evening'
  | 'continuous' | 'later' | 'unspecified';
export type ShotMovement =
  | 'static' | 'pan' | 'tilt' | 'dolly' | 'track' | 'zoom' | 'crane'
  | 'handheld' | 'steadicam' | 'aerial' | 'other';
export type CameraFraming =
  | 'establishing' | 'extreme_wide' | 'wide' | 'full' | 'medium' | 'medium_close'
  | 'close_up' | 'extreme_close_up' | 'insert' | 'other';
export type CameraAngle =
  | 'eye_level' | 'high' | 'low' | 'birds_eye' | 'worms_eye' | 'dutch'
  | 'over_shoulder' | 'pov' | 'other';
export type ShotApproval = 'draft' | 'in_review' | 'approved' | 'rejected' | 'superseded';

export const SCREEN_FORMATS: ScreenFormat[] = ['film', 'short', 'series', 'animation'];
export const SCREEN_PROJECT_STATUSES: ScreenProjectStatus[] = [
  'development', 'pre_production', 'production', 'post_production', 'delivered', 'on_hold', 'cancelled',
];
export const SCREEN_STATUSES: ScreenStatus[] = ['planned', 'in_progress', 'in_review', 'complete', 'on_hold'];
export const SCENE_ENVIRONMENTS: SceneEnvironment[] = ['int', 'ext', 'int_ext'];
export const SCENE_TIMES: SceneTimeOfDay[] = [
  'day', 'night', 'dawn', 'dusk', 'morning', 'evening', 'continuous', 'later', 'unspecified',
];
export const SHOT_MOVEMENTS: ShotMovement[] = [
  'static', 'pan', 'tilt', 'dolly', 'track', 'zoom', 'crane', 'handheld', 'steadicam', 'aerial', 'other',
];
export const CAMERA_FRAMINGS: CameraFraming[] = [
  'establishing', 'extreme_wide', 'wide', 'full', 'medium', 'medium_close',
  'close_up', 'extreme_close_up', 'insert', 'other',
];
export const CAMERA_ANGLES: CameraAngle[] = [
  'eye_level', 'high', 'low', 'birds_eye', 'worms_eye', 'dutch', 'over_shoulder', 'pov', 'other',
];
export const SHOT_APPROVALS: ShotApproval[] = ['draft', 'in_review', 'approved', 'rejected', 'superseded'];

export function scLabel(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export interface ScreenProject {
  id: string;
  dossier_id: string;
  source_work_id: string | null;
  story_world_id: string | null;
  title: string;
  format: ScreenFormat;
  status: ScreenProjectStatus;
  logline: string | null;
  synopsis: string | null;
  notes: string | null;
}

export interface ScreenUnit {
  id: string;
  screen_project_id: string;
  unit_type: ScreenUnitType;
  number: number;
  title: string | null;
  status: ScreenStatus;
  position: number;
}

export interface ScreenSequence {
  id: string;
  unit_id: string;
  sequence_number: number;
  title: string | null;
  description: string | null;
  status: ScreenStatus;
  position: number;
}

export interface SceneCharacter {
  id: string;
  scene_id: string;
  entity_id: string;
  entity_name: string | null;
  role: string | null;
  position: number;
}

export interface Shot {
  id: string;
  scene_id: string;
  shot_number: number;
  position: number;
  framing: CameraFraming | null;
  camera_angle: CameraAngle | null;
  movement: ShotMovement | null;
  lens: string | null;
  duration_seconds: number | null;
  blocking: string | null;
  lighting: string | null;
  dialogue: string | null;
  sound: string | null;
  music: string | null;
  vfx: string | null;
  source_storyboard_panel_id: string | null;
  status: ScreenStatus;
  approval: ShotApproval;
  mapped_panel_ids: string[];
  asset_version_ids: string[];
}

export interface Scene {
  id: string;
  sequence_id: string;
  scene_number: number;
  position: number;
  heading: string | null;
  location: string | null;
  environment: SceneEnvironment;
  time_of_day: SceneTimeOfDay;
  synopsis: string | null;
  script_text: string | null;
  estimated_duration_seconds: number | null;
  production_status: ScreenStatus;
  continuity_notes: string | null;
  shot_count: number;
}

export interface SceneDetail extends Scene {
  shots: Shot[];
  characters: SceneCharacter[];
}

export interface StoryboardRef {
  page_id: string;
  page_number: number;
  panel_id: string;
  panel_number: number;
}

export interface References {
  entities: { id: string; name: string; kind: string }[];
  rights: Record<string, unknown>[];
  provenance: Record<string, unknown>[];
}

export interface Breakdown {
  scenes: Record<string, unknown>[];
  totals: {
    scenes: number;
    shots: number;
    vfx_shots: number;
    locations: string[];
    characters: string[];
    estimated_duration_seconds: number;
  };
}
