// Admin (CMS) types for curating the public reader — the private projection.

export type PublishedStatus = 'draft' | 'published' | 'unlisted' | 'archived';

export interface PublishedWorkAdmin {
  id: string;
  created_at: string;
  updated_at: string;
  source_work_id: string | null;
  slug: string;
  title: string;
  subtitle: string | null;
  public_synopsis: string | null;
  cover_image: string | null;
  status: PublishedStatus;
  publication_date: string | null;
  author_credit: string | null;
  artist_credit: string | null;
  tags: string[];
  music_track_id: string | null;
  video_intro_id: string | null;
}

export interface VolumeAdmin {
  id: string;
  published_work_id: string;
  title: string;
  volume_number: number;
}

export interface ChapterAdmin {
  id: string;
  published_volume_id: string;
  title: string;
  chapter_number: number;
}

export interface PageAdmin {
  id: string;
  published_chapter_id: string;
  page_number: number;
  image_path: string;
  source_gn_page_id: string | null;
  source_asset_version_id: string | null;
}

export interface MediaAdmin {
  id: string;
  type: string;
  title: string;
  file_path: string;
  public_visibility: boolean;
}

export interface ValidationIssue {
  code: string;
  severity: string;
  message: string;
  target_id: string | null;
}

export interface ValidationResult {
  ok: boolean;
  errors: number;
  warnings: number;
  issues: ValidationIssue[];
}

export interface ApprovalAdmin {
  id: string;
  created_at: string;
  status: 'pending' | 'approved' | 'rejected';
  requested_by_id: string | null;
  decided_by_id: string | null;
  note: string | null;
}

export interface PublicationEventAdmin {
  id: string;
  created_at: string;
  action: string;
  actor_id: string | null;
  from_status: PublishedStatus | null;
  to_status: PublishedStatus | null;
  note: string | null;
}
