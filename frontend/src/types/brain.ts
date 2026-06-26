// Brain State Inspector types. The compiled `structured_state` is a deterministic
// but free-form JSON document, so it is typed as a record and rendered generically.

export interface StudioBrainState {
  id: string;
  version: number;
  status: string;
  compiled_at: string | null;
  source_event_cursor: number;
  structured_state: Record<string, unknown>;
  compact_summary: string | null;
  checksum: string | null;
  compiler_version: string | null;
  assist_version: string | null;
  stale: boolean;
}

export interface ProjectBrainState {
  id: string;
  work_id: string | null;
  story_world_id: string | null;
  version: number;
  status: string;
  compiled_at: string | null;
  source_event_cursor: number;
  structured_state: Record<string, unknown>;
  compact_summary: string | null;
  canon_digest: string | null;
  production_digest: string | null;
  open_questions: unknown[];
  priorities: unknown[];
  recent_changes: unknown[];
  checksum: string | null;
  stale: boolean;
}

export interface BrainEvent {
  id: string;
  sequence: number;
  event_type: string;
  aggregate_type: string;
  aggregate_id: string;
  work_id: string | null;
  story_world_id: string | null;
  actor_id: string | null;
  correlation_id: string | null;
  occurred_at?: string | null;
  status: string;
}

export interface BrainRevision {
  id: string;
  state_type: string;
  state_id: string;
  version: number;
  previous_version: number | null;
  source_event_from: number | null;
  source_event_to: number | null;
  compiler_version: string | null;
  generated_at: string;
}

export interface CompilerStateHealth {
  version: number;
  status: string;
  stale: boolean;
  checksum: string | null;
  compiled_at: string | null;
  source_event_cursor: number;
  lag: number;
  work_id?: string | null;
  story_world_id?: string | null;
}

export interface CompilerHealth {
  head_sequence: number;
  compiler_version: string;
  outbox: Record<string, number | boolean | null>;
  studio: CompilerStateHealth | null;
  projects: CompilerStateHealth[];
}

export interface StaleState {
  scope: string;
  id: string | null;
  work_id?: string | null;
  story_world_id?: string | null;
  version: number;
  stale: boolean;
  cursor: number;
  head: number;
  reason: string;
}

export interface StaleReport {
  head_sequence: number;
  count: number;
  states: StaleState[];
}

export interface RebuildResult {
  scope: string;
  version: number;
  checksum: string | null;
  changed: boolean;
  from_seq: number;
  to_seq: number;
  work_id?: string | null;
  story_world_id?: string | null;
}
