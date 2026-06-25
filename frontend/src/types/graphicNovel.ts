// Types for the detailed graphic-novel production hierarchy.

export type GNStatus = 'planned' | 'in_progress' | 'in_review' | 'complete' | 'on_hold';
export type StreamStatus = 'not_planned' | 'pending' | 'in_progress' | 'blocked' | 'complete';
export type PageSide = 'left' | 'right' | 'single';
export type PanelApproval = 'draft' | 'in_review' | 'approved' | 'rejected' | 'superseded';
export type CurationStatus = 'not_ready' | 'ready_for_curation' | 'in_curation' | 'handed_off';
export type PanelElementType = 'character' | 'prop' | 'location' | 'text';

export type CameraFraming =
  | 'establishing' | 'extreme_wide' | 'wide' | 'full' | 'medium' | 'medium_close'
  | 'close_up' | 'extreme_close_up' | 'insert' | 'other';
export type CameraAngle =
  | 'eye_level' | 'high' | 'low' | 'birds_eye' | 'worms_eye' | 'dutch'
  | 'over_shoulder' | 'pov' | 'other';

export const GN_STATUSES: GNStatus[] = ['planned', 'in_progress', 'in_review', 'complete', 'on_hold'];
export const STREAM_STATUSES: StreamStatus[] = ['not_planned', 'pending', 'in_progress', 'blocked', 'complete'];
export const PAGE_SIDES: PageSide[] = ['left', 'right', 'single'];
export const PANEL_APPROVALS: PanelApproval[] = ['draft', 'in_review', 'approved', 'rejected', 'superseded'];
export const CAMERA_FRAMINGS: CameraFraming[] = [
  'establishing', 'extreme_wide', 'wide', 'full', 'medium', 'medium_close',
  'close_up', 'extreme_close_up', 'insert', 'other',
];
export const CAMERA_ANGLES: CameraAngle[] = [
  'eye_level', 'high', 'low', 'birds_eye', 'worms_eye', 'dutch', 'over_shoulder', 'pov', 'other',
];

export function gnLabel(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export interface GNProduction {
  id: string;
  work_id: string;
  volume_number: number | null;
  script_status: StreamStatus;
  storyboard_status: StreamStatus;
  page_layout_status: StreamStatus;
  lettering_status: StreamStatus;
  coloring_status: StreamStatus;
  final_files_status: StreamStatus;
}

export interface TreeNode {
  id: string;
  label: string;
  kind: string;
  status: string;
  position: number;
  children: TreeNode[];
}

export interface PanelElement {
  id: string;
  panel_id: string;
  element_type: PanelElementType;
  entity_id: string | null;
  entity_name: string | null;
  text_content: string | null;
  asset_version_id: string | null;
  label: string | null;
  x: number | null;
  y: number | null;
  width: number | null;
  height: number | null;
  position: number;
}

export interface Panel {
  id: string;
  page_id: string;
  panel_number: number;
  position: number;
  status: GNStatus;
  x: number;
  y: number;
  width: number;
  height: number;
  script_beat: string | null;
  dialogue: string | null;
  captions: string | null;
  sound_effects: string | null;
  camera_framing: CameraFraming | null;
  camera_angle: CameraAngle | null;
  lens_metadata: string | null;
  continuity_notes: string | null;
  storyboard_asset_version_id: string | null;
  final_asset_version_id: string | null;
  approval_status: PanelApproval;
  elements: PanelElement[];
}

export interface PageEntityLink {
  id: string;
  page_id: string;
  entity_id: string;
  entity_name: string | null;
  role: string | null;
  position: number;
}

export interface Page {
  id: string;
  sequence_id: string;
  page_number: number;
  position: number;
  status: GNStatus;
  spread_id: string | null;
  page_side: PageSide;
  script: string | null;
  visual_brief: string | null;
  dialogue_summary: string | null;
  lettering_status: StreamStatus;
  colour_status: StreamStatus;
  final_status: StreamStatus;
  print_width_mm: number | null;
  print_height_mm: number | null;
  bleed_mm: number | null;
  safe_area_mm: number | null;
  master_asset_id: string | null;
  curation_status: CurationStatus;
  published_page_id: string | null;
  panel_count: number;
}

export interface PageDetail extends Page {
  panels: Panel[];
  entity_links: PageEntityLink[];
}

export interface Progress {
  pages_total: number;
  pages_complete: number;
  panels_total: number;
  panels_approved: number;
  lettering_complete: number;
  colour_complete: number;
  final_complete: number;
  overall_pct: number;
  panel_approval_pct: number;
}

export interface Readiness {
  print_ready: boolean;
  digital_ready: boolean;
  print_issues: string[];
  digital_issues: string[];
}

export interface ValidationIssue {
  level: string;
  target_id: string;
  message: string;
}

export interface ComparisonRow {
  panel_id: string;
  panel_number: number;
  storyboard: Record<string, unknown> | null;
  final: Record<string, unknown> | null;
}

export interface CurationHandoff {
  committed: boolean;
  eligible: { page_id: string; page_number: number }[];
  ineligible: { page_id: string; page_number: number; reasons: string[] }[];
}
