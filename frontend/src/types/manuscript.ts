import type { WorkflowStatus } from './workflow';

export type WorkType =
  | 'book'
  | 'graphic_novel'
  | 'novella'
  | 'anthology'
  | 'art_book'
  | 'other';

export const WORK_TYPES: WorkType[] = [
  'book',
  'graphic_novel',
  'novella',
  'anthology',
  'art_book',
  'other',
];

export const WORK_TYPE_LABELS: Record<WorkType, string> = {
  book: 'Book',
  graphic_novel: 'Graphic Novel',
  novella: 'Novella',
  anthology: 'Anthology',
  art_book: 'Art Book',
  other: 'Other',
};

export interface Manuscript {
  id: string;
  created_at: string;
  updated_at: string;
  title: string;
  subtitle: string | null;
  synopsis: string | null;
  work_type: WorkType;
  genre: string | null;
  language: string;
  word_count: number | null;
  status: WorkflowStatus;
  author_id: string;
}

export interface Author {
  id: string;
  created_at: string;
  updated_at: string;
  full_name: string;
  email: string | null;
  country: string | null;
  biography: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}
