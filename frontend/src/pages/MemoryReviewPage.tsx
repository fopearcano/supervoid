import { useEffect, useState } from 'react';
import { ApiError } from '@/api/client';
import {
  acceptMemory,
  editMemory,
  expireMemory,
  fetchMemoryInbox,
  mergeMemory,
  rejectMemory,
  supersedeMemory,
  type BrainMemoryItem,
} from '@/api/brain';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : 'Request failed';
}

const SCOPE_TONE: Record<string, 'accent' | 'live' | 'muted' | 'signal'> = {
  studio: 'signal',
  project: 'accent',
  member: 'live',
  conversation: 'muted',
};

export function MemoryReviewPage() {
  const [items, setItems] = useState<BrainMemoryItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const load = () => {
    fetchMemoryInbox()
      .then((rows) => setItems(rows))
      .catch((e) => setError(errMsg(e)));
  };

  useEffect(load, []);

  const run = async (id: string, fn: () => Promise<unknown>) => {
    setBusy(id);
    setError(null);
    try {
      await fn();
      setSelected((s) => {
        const next = new Set(s);
        next.delete(id);
        return next;
      });
      load();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(null);
    }
  };

  const toggle = (id: string) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const mergeSelected = () => {
    const ids = [...selected];
    if (ids.length < 2) return;
    const [primary, ...rest] = ids;
    run(primary, () => mergeMemory(primary, rest));
  };

  return (
    <div className="p-8">
      <Eyebrow>Brain · Memory</Eyebrow>
      <h2 className="mt-2 font-serif text-5xl text-parchment">Memory Review</h2>
      <p className="mt-2 max-w-2xl text-parchment-muted">
        Durable memory the Brain proposed from conversations. Nothing here is canon —
        accept what is true and useful, reject the rest. Canon, rights and production
        facts arrive as decisions to approve, never as memory. Edits and merges never
        overwrite: the original is kept and superseded.
      </p>

      {error && <p className="mt-4 font-mono text-[0.62rem] text-signal">{error}</p>}

      <div className="mt-6 flex items-center gap-3">
        <button type="button" className="button-ghost" onClick={load}>
          Refresh
        </button>
        <button
          type="button"
          className="button-ghost"
          onClick={mergeSelected}
          disabled={selected.size < 2}
        >
          Merge selected ({selected.size})
        </button>
      </div>

      {items.length === 0 ? (
        <p className="mt-10 font-serif italic text-parchment-muted">
          The review inbox is empty — no pending memory.
        </p>
      ) : (
        <ul className="mt-6 flex flex-col gap-3">
          {items.map((it) => (
            <li key={it.id} className="border border-rule p-4">
              <div className="flex flex-wrap items-center gap-2">
                <input
                  type="checkbox"
                  checked={selected.has(it.id)}
                  onChange={() => toggle(it.id)}
                  aria-label="Select for merge"
                />
                <Pill tone={SCOPE_TONE[it.scope] ?? 'muted'}>{it.scope}</Pill>
                <Pill>{it.kind}</Pill>
                {it.risk_level !== 'low' && <Pill tone="signal">risk: {it.risk_level}</Pill>}
                {it.confidence != null && (
                  <span className="font-mono text-[0.58rem] text-parchment-dim">
                    conf {Math.round(it.confidence * 100)}%
                  </span>
                )}
                {Array.isArray(it.structured_data?.contradicts) &&
                  (it.structured_data.contradicts as unknown[]).length > 0 && (
                    <Pill tone="signal">contradiction</Pill>
                  )}
                {it.structured_data?.previously_rejected === true && (
                  <Pill tone="signal">previously rejected</Pill>
                )}
              </div>

              <p className="mt-3 text-parchment">{it.content}</p>

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="button-accent"
                  disabled={busy === it.id}
                  onClick={() => run(it.id, () => acceptMemory(it.id))}
                >
                  Accept
                </button>
                <button
                  type="button"
                  className="button-ghost"
                  disabled={busy === it.id}
                  onClick={() => run(it.id, () => rejectMemory(it.id))}
                >
                  Reject
                </button>
                <button
                  type="button"
                  className="button-ghost"
                  disabled={busy === it.id}
                  onClick={() => {
                    const next = window.prompt('Edit memory (supersedes the original):', it.content);
                    if (next && next.trim()) run(it.id, () => editMemory(it.id, next.trim()));
                  }}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className="button-ghost"
                  disabled={busy === it.id}
                  onClick={() => {
                    const next = window.prompt('Replace with a verified successor:', it.content);
                    if (next && next.trim()) run(it.id, () => supersedeMemory(it.id, next.trim()));
                  }}
                >
                  Supersede
                </button>
                <button
                  type="button"
                  className="button-ghost"
                  disabled={busy === it.id}
                  onClick={() => run(it.id, () => expireMemory(it.id))}
                >
                  Expire
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
