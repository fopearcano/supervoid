import { useEffect, useState } from 'react';
import { ApiError } from '@/api/client';
import { createStoryWorld, fetchStoryWorlds } from '@/api/transmedia';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import {
  WORLD_STATUSES,
  WORLD_STATUS_LABELS,
  type StoryWorld,
  type StoryWorldStatus,
} from '@/types/transmedia';

interface Props {
  onOpenWorld: (id: string) => void;
}

export function StoryWorldsPage({ onOpenWorld }: Props) {
  const [worlds, setWorlds] = useState<StoryWorld[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [status, setStatus] = useState<StoryWorldStatus>('developing');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);

  const load = () => {
    fetchStoryWorlds()
      .then((page) => setWorlds(page.items))
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : 'Failed to load story worlds.'),
      );
  };

  useEffect(load, []);

  const submit = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createStoryWorld({
        name: name.trim(),
        status,
        description: description.trim() || null,
      });
      setName('');
      setDescription('');
      setStatus('developing');
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to create story world.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-14">
      <header>
        <Eyebrow>Studio · intellectual properties</Eyebrow>
        <h2 className="mt-3 font-serif text-5xl leading-tight text-parchment">
          Story Worlds
        </h2>
        <p className="mt-4 max-w-prose text-parchment-muted">
          The universes above the catalogue. A story world gathers its series and
          Works across every medium and division — books, pictures, audio,
          interactive — while each Work still owns its own production.
        </p>
      </header>

      {/* Create */}
      <section className="border border-rule p-6">
        <Eyebrow>New story world</Eyebrow>
        <div className="mt-4 grid gap-3 sm:grid-cols-[1fr,12rem]">
          <input
            className="field-input"
            placeholder="Name (e.g. The Silent Workshop)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <select
            className="field-select"
            value={status}
            onChange={(e) => setStatus(e.target.value as StoryWorldStatus)}
          >
            {WORLD_STATUSES.map((s) => (
              <option key={s} value={s}>
                {WORLD_STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </div>
        <textarea
          className="field-input mt-3 w-full"
          rows={2}
          placeholder="Short description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <div className="mt-4 flex items-center gap-4">
          <button
            type="button"
            className="button-accent"
            onClick={submit}
            disabled={busy || !name.trim()}
          >
            Create world
          </button>
          {error && (
            <span className="font-mono text-[0.66rem] uppercase tracking-widest text-signal">
              {error}
            </span>
          )}
        </div>
      </section>

      {/* List */}
      <section>
        <div className="flex items-baseline justify-between border-b border-rule pb-3">
          <span className="font-mono text-[0.65rem] uppercase tracking-widest text-parchment-dim">
            Worlds
          </span>
          <span className="font-mono text-[0.65rem] uppercase tracking-widest text-parchment-muted">
            {worlds === null ? 'Loading…' : `${worlds.length}`}
          </span>
        </div>

        {worlds !== null && worlds.length === 0 && (
          <p className="py-12 font-serif italic text-parchment-muted">
            No story worlds yet. Create one above to begin building an IP.
          </p>
        )}

        {worlds !== null && worlds.length > 0 && (
          <ul className="border-b border-rule">
            {worlds.map((w) => (
              <li key={w.id} className="border-t border-rule">
                <button
                  type="button"
                  onClick={() => onOpenWorld(w.id)}
                  className="flex w-full flex-wrap items-baseline justify-between gap-3 px-1 py-5 text-left transition-colors hover:bg-ink-700/40"
                >
                  <div>
                    <div className="font-serif text-[1.2rem] text-parchment">
                      {w.name}
                    </div>
                    <div className="mt-1 font-mono text-[0.6rem] uppercase tracking-widest text-parchment-dim">
                      {w.slug} · {w.default_language.toUpperCase()}
                    </div>
                    {w.description && (
                      <p className="mt-2 max-w-prose text-sm text-parchment-muted/80">
                        {w.description}
                      </p>
                    )}
                  </div>
                  <Pill tone={w.status === 'active' ? 'live' : 'muted'}>
                    {WORLD_STATUS_LABELS[w.status]}
                  </Pill>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
