import { publicFetch } from './publicClient';
import type {
  PublicHotspot,
  PublicMediaAsset,
  PublishedChapter,
  PublishedPage,
  PublishedVolume,
  PublishedWorkDetail,
  PublishedWorkSummary,
} from '../types/reader';

const enc = encodeURIComponent;

export const listWorks = () =>
  publicFetch<PublishedWorkSummary[]>('/works');

export const getWork = (slug: string) =>
  publicFetch<PublishedWorkDetail>(`/works/${enc(slug)}`);

export const listVolumes = (slug: string) =>
  publicFetch<PublishedVolume[]>(`/works/${enc(slug)}/volumes`);

export const listChapters = (volumeId: string) =>
  publicFetch<PublishedChapter[]>(`/volumes/${enc(volumeId)}/chapters`);

export const listPages = (chapterId: string) =>
  publicFetch<PublishedPage[]>(`/chapters/${enc(chapterId)}/pages`);

export const getPage = (pageId: string) =>
  publicFetch<PublishedPage>(`/pages/${enc(pageId)}`);

export const listHotspots = (pageId: string) =>
  publicFetch<PublicHotspot[]>(`/pages/${enc(pageId)}/hotspots`);

export const getMedia = (id: string) =>
  publicFetch<PublicMediaAsset>(`/media/${enc(id)}`);
