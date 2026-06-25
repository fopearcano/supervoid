// Types for the central Asset Library (mirrors the backend schemas).
import type { CanonState } from '@/types/transmedia';

export type AssetType =
  | 'image' | 'illustration' | 'character_design' | 'environment_design'
  | 'cover' | 'page_art' | 'storyboard' | 'concept_art' | 'audio' | 'music'
  | 'sound_effect' | 'voice' | 'video' | 'animation' | 'model_3d' | 'texture'
  | 'font' | 'script' | 'document' | 'other';

export type AssetVisibility =
  | 'private' | 'internal' | 'restricted' | 'public_candidate';

export type AssetApprovalStatus =
  | 'draft' | 'in_review' | 'approved' | 'rejected' | 'superseded';

export type ProvenanceKind =
  | 'human_created' | 'ai_assisted' | 'ai_generated' | 'mixed';

export type CommercialUseReviewStatus =
  | 'not_reviewed' | 'under_review' | 'cleared' | 'restricted' | 'blocked';

export type LicenceType =
  | 'proprietary' | 'commissioned' | 'work_for_hire' | 'stock'
  | 'creative_commons' | 'public_domain' | 'royalty_free' | 'rights_managed'
  | 'ai_generated' | 'other';

export type LicenceReviewState =
  | 'not_reviewed' | 'pending' | 'approved' | 'rejected' | 'expired';

export type AssetLinkTargetType =
  | 'character' | 'location' | 'knowledge_entity' | 'page' | 'panel' | 'scene'
  | 'shot' | 'production_task' | 'public_reader_record' | 'work' | 'story_world'
  | 'other';

function titleize(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export const ASSET_TYPES: AssetType[] = [
  'image', 'illustration', 'character_design', 'environment_design', 'cover',
  'page_art', 'storyboard', 'concept_art', 'audio', 'music', 'sound_effect',
  'voice', 'video', 'animation', 'model_3d', 'texture', 'font', 'script',
  'document', 'other',
];
export const VISIBILITIES: AssetVisibility[] = [
  'private', 'internal', 'restricted', 'public_candidate',
];
export const APPROVAL_STATUSES: AssetApprovalStatus[] = [
  'draft', 'in_review', 'approved', 'rejected', 'superseded',
];
export const PROVENANCE_KINDS: ProvenanceKind[] = [
  'human_created', 'ai_assisted', 'ai_generated', 'mixed',
];
export const LICENCE_TYPES: LicenceType[] = [
  'proprietary', 'commissioned', 'work_for_hire', 'stock', 'creative_commons',
  'public_domain', 'royalty_free', 'rights_managed', 'ai_generated', 'other',
];
export const LICENCE_REVIEW_STATES: LicenceReviewState[] = [
  'not_reviewed', 'pending', 'approved', 'rejected', 'expired',
];

export const label = titleize;

export interface Asset {
  id: string;
  created_at: string;
  updated_at: string;
  title: string;
  asset_type: AssetType;
  work_id: string | null;
  story_world_id: string | null;
  canon_status: CanonState;
  visibility: AssetVisibility;
  owner_id: string | null;
  owner_name: string | null;
  tags: string[];
  description: string | null;
  current_version_id: string | null;
  version_count: number;
}

export interface AssetVersion {
  id: string;
  created_at: string;
  updated_at: string;
  asset_id: string;
  version_number: number;
  storage_key: string;
  mime_type: string;
  size_bytes: number;
  checksum: string | null;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  creator_id: string | null;
  creator_name: string | null;
  approval_status: AssetApprovalStatus;
  superseded_by_id: string | null;
  technical_metadata: Record<string, unknown>;
  notes: string | null;
  is_placeholder: boolean;
  is_current: boolean;
  has_provenance: boolean;
}

export interface AssetDetail extends Asset {
  versions: AssetVersion[];
  current_version: AssetVersion | null;
  link_count: number;
  licence_count: number;
}

export interface Provenance {
  id: string;
  asset_version_id: string;
  kind: ProvenanceKind;
  provider: string | null;
  base_model: string | null;
  base_model_version: string | null;
  adapter_identifiers: string | null;
  prompt: string | null;
  negative_prompt: string | null;
  seed: number | null;
  sampler: string | null;
  settings: Record<string, unknown>;
  source_references: string | null;
  controlnet_inputs: string | null;
  generating_workflow: string | null;
  human_modifications: string | null;
  generation_date: string | null;
  responsible_user_id: string | null;
  responsible_user_name: string | null;
  commercial_use_review: CommercialUseReviewStatus;
}

export interface ProvenanceCompleteness {
  complete: boolean;
  missing: string[];
  recommended: string[];
}

export interface Licence {
  id: string;
  asset_id: string;
  rights_holder: string | null;
  licence_type: LicenceType;
  source: string | null;
  territory: string | null;
  permitted_uses: string | null;
  attribution_requirements: string | null;
  expiration_date: string | null;
  evidence_storage_key: string | null;
  review_state: LicenceReviewState;
  notes: string | null;
}

export interface AssetLink {
  id: string;
  asset_id: string;
  asset_version_id: string | null;
  target_type: AssetLinkTargetType;
  target_id: string;
  role: string | null;
  note: string | null;
}

export interface LicenceWarning {
  licence_id: string;
  asset_id: string;
  licence_type: string;
  expiration_date: string | null;
  status: string;
  days_remaining: number | null;
}
