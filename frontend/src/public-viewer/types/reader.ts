// Public reader types — mirror backend `schemas/public_reader.py`. Public-safe
// only: there is intentionally no private editorial data in these shapes.

export type PublishedStatus = 'draft' | 'published' | 'unlisted' | 'archived';
export type MediaAssetType = 'image' | 'audio' | 'video';
export type HotspotType =
  | 'info'
  | 'character'
  | 'location'
  | 'lore'
  | 'external_link'
  | 'audio'
  | 'video';

export const HOTSPOT_LABELS: Record<HotspotType, string> = {
  info: 'Note',
  character: 'Character',
  location: 'Location',
  lore: 'Lore',
  external_link: 'Link',
  audio: 'Audio',
  video: 'Video',
};

export interface PublicMediaAsset {
  id: string;
  type: MediaAssetType;
  title: string;
  file_path: string;
  poster_image: string | null;
  duration: number | null;
  loop: boolean;
  credits: string | null;
}

export interface PublicHotspot {
  id: string;
  type: HotspotType;
  x: number;
  y: number;
  width: number;
  height: number;
  title: string;
  content: string | null;
  target_url: string | null;
  audio_track: PublicMediaAsset | null;
  video: PublicMediaAsset | null;
}

export interface PublishedPage {
  id: string;
  page_number: number;
  image_path: string;
  alt_text: string | null;
  width: number | null;
  height: number | null;
  music_track: PublicMediaAsset | null;
  video_overlay: PublicMediaAsset | null;
  hotspots: PublicHotspot[];
}

export interface PublishedChapterSummary {
  id: string;
  title: string;
  chapter_number: number;
  public_description: string | null;
  page_count: number;
}

export interface PublishedChapter extends PublishedChapterSummary {
  music_track: PublicMediaAsset | null;
  video_intro: PublicMediaAsset | null;
}

export interface PublishedVolume {
  id: string;
  title: string;
  volume_number: number;
  public_description: string | null;
  cover_image: string | null;
  publication_date: string | null;
  music_track: PublicMediaAsset | null;
  chapters: PublishedChapterSummary[];
}

export interface PublishedWorkSummary {
  id: string;
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
}

export interface PublishedWorkDetail extends PublishedWorkSummary {
  music_track: PublicMediaAsset | null;
  video_intro: PublicMediaAsset | null;
  volumes: PublishedVolume[];
}

export type ReaderMode = 'single' | 'double' | 'scroll' | 'cinematic';

export const READER_MODE_LABELS: Record<ReaderMode, string> = {
  single: 'Single page',
  double: 'Double spread',
  scroll: 'Vertical scroll',
  cinematic: 'Cinematic',
};
