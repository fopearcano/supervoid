// Types for the IP / transmedia studio layer (mirrors the backend schemas).

export type StudioDivision =
  | 'publishing'
  | 'pictures'
  | 'interactive'
  | 'audio'
  | 'cross_media';

export type Medium =
  | 'book'
  | 'graphic_novel'
  | 'film'
  | 'short_film'
  | 'series'
  | 'animation'
  | 'audio_drama'
  | 'web_experience'
  | 'game'
  | 'other';

export type CanonState =
  | 'canon'
  | 'soft_canon'
  | 'alternate'
  | 'non_canon'
  | 'undecided';

export type AdaptationStatus =
  | 'proposed'
  | 'optioned'
  | 'in_development'
  | 'in_production'
  | 'released'
  | 'on_hold'
  | 'abandoned';

export type RightsClearanceState =
  | 'not_started'
  | 'in_progress'
  | 'cleared'
  | 'blocked'
  | 'not_required';

export type StoryWorldStatus = 'developing' | 'active' | 'dormant' | 'archived';

export type StorySeriesStatus =
  | 'planned'
  | 'ongoing'
  | 'complete'
  | 'on_hold'
  | 'archived';

export const DIVISION_LABELS: Record<StudioDivision, string> = {
  publishing: 'Publishing',
  pictures: 'Pictures',
  interactive: 'Interactive',
  audio: 'Audio',
  cross_media: 'Cross-media',
};

export const MEDIUM_LABELS: Record<Medium, string> = {
  book: 'Book',
  graphic_novel: 'Graphic novel',
  film: 'Film',
  short_film: 'Short film',
  series: 'Series',
  animation: 'Animation',
  audio_drama: 'Audio drama',
  web_experience: 'Web experience',
  game: 'Game',
  other: 'Other',
};

export const CANON_LABELS: Record<CanonState, string> = {
  canon: 'Canon',
  soft_canon: 'Soft canon',
  alternate: 'Alternate',
  non_canon: 'Non-canon',
  undecided: 'Undecided',
};

export const ADAPTATION_STATUS_LABELS: Record<AdaptationStatus, string> = {
  proposed: 'Proposed',
  optioned: 'Optioned',
  in_development: 'In development',
  in_production: 'In production',
  released: 'Released',
  on_hold: 'On hold',
  abandoned: 'Abandoned',
};

export const RIGHTS_CLEARANCE_LABELS: Record<RightsClearanceState, string> = {
  not_started: 'Not started',
  in_progress: 'In progress',
  cleared: 'Cleared',
  blocked: 'Blocked',
  not_required: 'Not required',
};

export const WORLD_STATUS_LABELS: Record<StoryWorldStatus, string> = {
  developing: 'Developing',
  active: 'Active',
  dormant: 'Dormant',
  archived: 'Archived',
};

export const SERIES_STATUS_LABELS: Record<StorySeriesStatus, string> = {
  planned: 'Planned',
  ongoing: 'Ongoing',
  complete: 'Complete',
  on_hold: 'On hold',
  archived: 'Archived',
};

export const DIVISIONS = Object.keys(DIVISION_LABELS) as StudioDivision[];
export const MEDIA = Object.keys(MEDIUM_LABELS) as Medium[];
export const CANON_STATES = Object.keys(CANON_LABELS) as CanonState[];
export const ADAPTATION_STATUSES = Object.keys(
  ADAPTATION_STATUS_LABELS,
) as AdaptationStatus[];
export const RIGHTS_CLEARANCE_STATES = Object.keys(
  RIGHTS_CLEARANCE_LABELS,
) as RightsClearanceState[];
export const WORLD_STATUSES = Object.keys(WORLD_STATUS_LABELS) as StoryWorldStatus[];
export const SERIES_STATUSES = Object.keys(
  SERIES_STATUS_LABELS,
) as StorySeriesStatus[];

export interface StoryWorld {
  id: string;
  created_at: string;
  updated_at: string;
  name: string;
  slug: string;
  description: string | null;
  canon_summary: string | null;
  status: StoryWorldStatus;
  visual_identity_notes: string | null;
  default_language: string;
  owner_id: string | null;
  parent_id: string | null;
}

export interface StorySeries {
  id: string;
  created_at: string;
  updated_at: string;
  story_world_id: string;
  title: string;
  description: string | null;
  sequence_order: number;
  status: StorySeriesStatus;
}

export interface AdaptationDossier {
  id: string;
  created_at: string;
  updated_at: string;
  source_work_id: string;
  source_work_title: string | null;
  target_work_id: string | null;
  target_work_title: string | null;
  target_medium: Medium;
  target_division: StudioDivision;
  status: AdaptationStatus;
  logline: string | null;
  format: string | null;
  intended_scope: string | null;
  rights_clearance: RightsClearanceState;
  creative_notes: string | null;
  source_revision: string | null;
}

// A Work as surfaced by the transmedia endpoints. (The admin app is otherwise
// manuscript-centric; this is the Work-aware view.)
export interface TransmediaWork {
  id: string;
  created_at: string;
  updated_at: string;
  title: string;
  subtitle: string | null;
  work_type: string;
  genre: string | null;
  status: string;
  author_id: string;
  story_world_id: string | null;
  story_series_id: string | null;
  series_order: number | null;
  primary_division: StudioDivision;
  primary_medium: Medium | null;
  canon_status: CanonState;
  source_work_id: string | null;
}

export interface WorkTransmediaOverview {
  work: TransmediaWork;
  story_world: StoryWorld | null;
  story_series: StorySeries | null;
  source_work: TransmediaWork | null;
  derived_works: TransmediaWork[];
  adaptation_dossiers: AdaptationDossier[];
}
