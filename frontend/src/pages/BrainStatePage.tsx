import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '@/api/client';
import {
  fetchCompilerHealth,
  fetchEvents,
  fetchStale,
  fetchStudioState,
  fetchWorkState,
  processOutbox,
  rebuildStudio,
  rebuildWork,
  reconcileOutbox,
} from '@/api/brain';
import { useAuth } from '@/auth/AuthContext';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import type {
  BrainEvent,
  CompilerHealth,
  ProjectBrainState,
  StaleReport,
  StudioBrainState,
} from '@/types/brain';

type Tab = 'studio' | 'project' | 'deltas' | 'health';

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : 'Request failed';
}

function StateHeader({
  version,
  status,
  cursor,
  checksum,
  stale,
  compiledAt,
}: {
  version: number;
  status: string;
  cursor: number;
  checksum: string | null;
  stale: boolean;
  compiledAt: string | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Pill tone={stale ? 'signal' : 'live'}>{stale ? 'stale' : status}</Pill>
      <span className="font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
        v{version} · cursor {cursor} · {checksum ? checksum.slice(0, 12) : '—'} ·{' '}
        {compiledAt ? new Date(compiledAt).toLocaleString() : 'never'}
      </span>
    </div>
  );
}

function FactsPanel({ summary, state }: { summary: string | null; state: Record<string, unknown> }) {
  return (
    <div className="mt-4 space-y-4">
      {summary && (
        <div className="border border-rule p-3">
          <Eyebrow>Compact summary</Eyebrow>
          <pre className="mt-2 whitespace-pre-wrap font-mono text-[0.66rem] text-parchment">{summary}</pre>
        </div>
      )}
      <div className="border border-rule p-3">
        <Eyebrow>Compiled facts (deterministic)</Eyebrow>
        <pre className="mt-2 max-h-[28rem] overflow-auto font-mono text-[0.6rem] text-parchment-muted">
          {JSON.stringify(state, null, 2)}
        </pre>
      </div>
    </div>
  );
}

export function BrainStatePage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>('studio');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [studio, setStudio] = useState<StudioBrainState | null>(null);
  const [workId, setWorkId] = useState('');
  const [project, setProject] = useState<ProjectBrainState | null>(null);
  const [events, setEvents] = useState<BrainEvent[]>([]);
  const [health, setHealth] = useState<CompilerHealth | null>(null);
  const [stale, setStale] = useState<StaleReport | null>(null);

  const loadStudio = useCallback(() => {
    fetchStudioState().then(setStudio).catch((e) => setError(errMsg(e)));
  }, []);
  const loadHealth = useCallback(() => {
    fetchCompilerHealth().then(setHealth).catch((e) => setError(errMsg(e)));
    fetchStale().then(setStale).catch((e) => setError(errMsg(e)));
  }, []);
  const loadEvents = useCallback(() => {
    fetchEvents({ limit: 50 }).then(setEvents).catch((e) => setError(errMsg(e)));
  }, []);

  useEffect(() => {
    if (user?.role !== 'admin') return;
    if (tab === 'studio') loadStudio();
    if (tab === 'deltas') loadEvents();
    if (tab === 'health') loadHealth();
  }, [tab, user, loadStudio, loadEvents, loadHealth]);

  if (user?.role !== 'admin') {
    return (
      <div className="p-8">
        <Eyebrow>Brain</Eyebrow>
        <h2 className="mt-2 font-serif text-3xl text-parchment">Brain State</h2>
        <p className="mt-4 text-parchment-muted">
          The Brain State Inspector is restricted to administrators.
        </p>
      </div>
    );
  }

  const run = async (fn: () => Promise<unknown>, after?: () => void) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      after?.();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  const loadProject = () => {
    if (!workId.trim()) return;
    fetchWorkState(workId.trim()).then(setProject).catch((e) => setError(errMsg(e)));
  };

  const TABS: { id: Tab; label: string }[] = [
    { id: 'studio', label: 'Studio Facts' },
    { id: 'project', label: 'Project Facts' },
    { id: 'deltas', label: 'Recent Deltas' },
    { id: 'health', label: 'Health & Rebuild' },
  ];

  return (
    <div className="p-8">
      <Eyebrow>Brain</Eyebrow>
      <h2 className="mt-2 font-serif text-5xl text-parchment">Brain State</h2>
      <p className="mt-2 max-w-2xl text-parchment-muted">
        The compiled, ready-to-use mental state — deterministic facts plus a compact summary,
        versioned and event-cursored. Rebuilds are deterministic; prose never overwrites facts.
      </p>

      <div className="mt-6 flex gap-4 border-b border-rule">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={tab === t.id ? 'nav-link-active' : 'nav-link'}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <p className="mt-4 font-mono text-[0.62rem] text-signal">{error}</p>}

      {tab === 'studio' && (
        <div className="mt-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            {studio ? (
              <StateHeader
                version={studio.version}
                status={studio.status}
                cursor={studio.source_event_cursor}
                checksum={studio.checksum}
                stale={studio.stale}
                compiledAt={studio.compiled_at}
              />
            ) : (
              <span className="text-parchment-muted">No studio state compiled yet.</span>
            )}
            <div className="flex gap-2">
              <button type="button" disabled={busy} className="button-accent"
                onClick={() => run(() => rebuildStudio(false), loadStudio)}>
                Rebuild (incremental)
              </button>
              <button type="button" disabled={busy} className="button-outline"
                onClick={() => run(() => rebuildStudio(true), loadStudio)}>
                Full rebuild
              </button>
            </div>
          </div>
          {studio && <FactsPanel summary={studio.compact_summary} state={studio.structured_state} />}
        </div>
      )}

      {tab === 'project' && (
        <div className="mt-6">
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={workId}
              onChange={(e) => setWorkId(e.target.value)}
              placeholder="Work id…"
              className="border border-rule bg-ink-800 px-3 py-1 font-mono text-[0.7rem] text-parchment"
            />
            <button type="button" className="button-outline" onClick={loadProject}>Load</button>
            {project && (
              <>
                <button type="button" disabled={busy} className="button-accent"
                  onClick={() => run(() => rebuildWork(workId.trim(), false), loadProject)}>
                  Rebuild
                </button>
                <button type="button" disabled={busy} className="button-outline"
                  onClick={() => run(() => rebuildWork(workId.trim(), true), loadProject)}>
                  Full rebuild
                </button>
              </>
            )}
          </div>
          {project ? (
            <>
              <div className="mt-4">
                <StateHeader
                  version={project.version}
                  status={project.status}
                  cursor={project.source_event_cursor}
                  checksum={project.checksum}
                  stale={project.stale}
                  compiledAt={project.compiled_at}
                />
              </div>
              <FactsPanel summary={project.compact_summary} state={project.structured_state} />
            </>
          ) : (
            <p className="mt-4 text-parchment-muted">Enter a Work id to inspect its compiled state.</p>
          )}
        </div>
      )}

      {tab === 'deltas' && (
        <div className="mt-6">
          <Eyebrow>Recent domain events (newest first)</Eyebrow>
          <table className="mt-3 w-full border-collapse font-mono text-[0.62rem]">
            <thead>
              <tr className="text-parchment-dim">
                <th className="border-b border-rule py-1 text-left">seq</th>
                <th className="border-b border-rule py-1 text-left">event</th>
                <th className="border-b border-rule py-1 text-left">aggregate</th>
                <th className="border-b border-rule py-1 text-left">status</th>
              </tr>
            </thead>
            <tbody>
              {[...events].reverse().map((e) => (
                <tr key={e.id} className="text-parchment-muted">
                  <td className="border-b border-rule/40 py-1">{e.sequence}</td>
                  <td className="border-b border-rule/40 py-1 text-parchment">{e.event_type}</td>
                  <td className="border-b border-rule/40 py-1">{e.aggregate_type}/{e.aggregate_id.slice(0, 8)}</td>
                  <td className="border-b border-rule/40 py-1">{e.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'health' && (
        <div className="mt-6 space-y-4">
          <div className="flex gap-2">
            <button type="button" disabled={busy} className="button-outline"
              onClick={() => run(() => processOutbox(), loadHealth)}>Process backlog</button>
            <button type="button" disabled={busy} className="button-quiet"
              onClick={() => run(() => reconcileOutbox(), loadHealth)}>Reconcile</button>
          </div>
          {health && (
            <div className="border border-rule p-3">
              <Eyebrow>Compiler health</Eyebrow>
              <p className="mt-2 font-mono text-[0.62rem] text-parchment-muted">
                head {health.head_sequence} · compiler {health.compiler_version} · studio v
                {health.studio?.version ?? 0} (lag {health.studio?.lag ?? '—'}) · {health.projects.length} project states
              </p>
            </div>
          )}
          {stale && (
            <div className="border border-rule p-3">
              <Eyebrow>Stale states ({stale.count})</Eyebrow>
              {stale.states.length === 0 ? (
                <p className="mt-2 text-parchment-muted">Everything is current.</p>
              ) : (
                <ul className="mt-2 space-y-1 font-mono text-[0.62rem] text-parchment-muted">
                  {stale.states.map((s, i) => (
                    <li key={i}>
                      {s.scope}{s.work_id ? `:${s.work_id.slice(0, 8)}` : ''} — {s.reason} (cursor{' '}
                      {s.cursor}/{s.head})
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
