import { useEffect, useState } from 'react';
import { ApiError } from '@/api/client';
import {
  createStorySeries,
  fetchStorySeries,
  fetchStoryWorld,
  fetchWorks,
  patchStorySeries,
  patchStoryWorld,
} from '@/api/transmedia';
import { AskBrainButton } from '@/components/AskBrainButton';
import { CollaboratorsPanel } from '@/components/CollaboratorsPanel';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import {
  CANON_LABELS,
  DIVISION_LABELS,
  MEDIUM_LABELS,
  SERIES_STATUSES,
  SERIES_STATUS_LABELS,
  WORLD_STATUSES,
  WORLD_STATUS_LABELS,
  type StorySeries,
  type StorySeriesStatus,
  type StoryWorld,
  type StoryWorldStatus,
  type TransmediaWork,
} from '@/types/transmedia';

interface Props {
  worldId: string;
  onBack: () => void;
  onOpenWork: (id: string) => void;
}

export function StoryWorldDetailPage({ worldId, onBack, onOpenWork }: Props) {
  const [world, setWorld] = useState<StoryWorld | null>(null);
  const [series, setSeries] = useState<StorySeries[]>([]);
  const [works, setWorks] = useState<TransmediaWork[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [seriesTitle, setSeriesTitle] = useState('');
  const [seriesOrder, setSeriesOrder] = useState(1);

  const loadAll = () => {
    fetchStoryWorld(worldId)
      .then(setWorld)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Load failed.'));
    fetchStorySeries(worldId).then((p) => setSeries(p.items)).catch(() => undefined);
    fetchWorks({ story_world_id: worldId }).then((p) => setWorks(p.items)).catch(() => undefined);
  };

  useEffect(loadAll, [worldId]);

  const changeWorldStatus = async (status: StoryWorldStatus) => {
    const updated = await patchStoryWorld(worldId, { status });
    setWorld(updated);
  };

  const addSeries = async () => {
    if (!seriesTitle.trim()) return;
    await createStorySeries({
      story_world_id: worldId,
      title: seriesTitle.trim(),
      sequence_order: seriesOrder,
    });
    setSeriesTitle('');
    setSeriesOrder((n) => n + 1);
    fetchStorySeries(worldId).then((p) => setSeries(p.items));
  };

  const changeSeriesStatus = async (id: string, status: StorySeriesStatus) => {
    await patchStorySeries(id, { status });
    fetchStorySeries(worldId).then((p) => setSeries(p.items));
  };

  if (error) {
    return (
      <p className="font-mono text-[0.7rem] uppercase tracking-widest text-signal">
        {error}
      </p>
    );
  }
  if (!world) {
    return <p className="font-mono text-[0.7rem] uppercase tracking-widest text-parchment-dim">Loading…</p>;
  }

  return (
    <div className="flex flex-col gap-14">
      <header>
        <button
          type="button"
          onClick={onBack}
          className="font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim hover:text-parchment"
        >
          ← Story Worlds
        </button>
        <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
          <div>
            <Eyebrow>Story world · {world.slug}</Eyebrow>
            <h2 className="mt-2 font-serif text-5xl leading-tight text-parchment">
              {world.name}
            </h2>
          </div>
          <div className="flex items-center gap-3">
            <select
              className="field-select"
              value={world.status}
              onChange={(e) => changeWorldStatus(e.target.value as StoryWorldStatus)}
              aria-label="World status"
            >
              {WORLD_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {WORLD_STATUS_LABELS[s]}
                </option>
              ))}
            </select>
            <AskBrainButton entityType="story_world" entityId={world.id} />
          </div>
        </div>
        {world.description && (
          <p className="mt-4 max-w-prose text-parchment-muted">{world.description}</p>
        )}
      </header>

      {(world.canon_summary || world.visual_identity_notes) && (
        <section className="grid gap-8 sm:grid-cols-2">
          {world.canon_summary && (
            <div>
              <Eyebrow>Canon summary</Eyebrow>
              <p className="editorial-prose mt-3 text-[0.95rem]">{world.canon_summary}</p>
            </div>
          )}
          {world.visual_identity_notes && (
            <div>
              <Eyebrow>Visual identity</Eyebrow>
              <p className="editorial-prose mt-3 text-[0.95rem]">
                {world.visual_identity_notes}
              </p>
            </div>
          )}
        </section>
      )}

      {/* Series */}
      <section>
        <div className="flex items-baseline justify-between border-b border-rule pb-3">
          <span className="font-mono text-[0.65rem] uppercase tracking-widest text-parchment-dim">
            Series
          </span>
          <span className="font-mono text-[0.65rem] uppercase tracking-widest text-parchment-muted">
            {series.length}
          </span>
        </div>
        <ul>
          {series.map((s) => (
            <li
              key={s.id}
              className="flex flex-wrap items-center justify-between gap-3 border-b border-rule py-4"
            >
              <div>
                <span className="font-mono text-[0.62rem] text-parchment-shadow">
                  {String(s.sequence_order).padStart(2, '0')}
                </span>{' '}
                <span className="font-serif text-[1.05rem] text-parchment">{s.title}</span>
                {s.description && (
                  <p className="mt-1 text-sm text-parchment-muted/70">{s.description}</p>
                )}
              </div>
              <select
                className="field-select"
                value={s.status}
                onChange={(e) =>
                  changeSeriesStatus(s.id, e.target.value as StorySeriesStatus)
                }
                aria-label="Series status"
              >
                {SERIES_STATUSES.map((st) => (
                  <option key={st} value={st}>
                    {SERIES_STATUS_LABELS[st]}
                  </option>
                ))}
              </select>
            </li>
          ))}
        </ul>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <input
            className="field-input"
            placeholder="New series title"
            value={seriesTitle}
            onChange={(e) => setSeriesTitle(e.target.value)}
          />
          <input
            type="number"
            className="field-input w-24"
            value={seriesOrder}
            onChange={(e) => setSeriesOrder(Number(e.target.value))}
            aria-label="Sequence order"
          />
          <button
            type="button"
            className="button-accent"
            onClick={addSeries}
            disabled={!seriesTitle.trim()}
          >
            Add series
          </button>
        </div>
      </section>

      {/* Works in the world */}
      <section>
        <div className="flex items-baseline justify-between border-b border-rule pb-3">
          <span className="font-mono text-[0.65rem] uppercase tracking-widest text-parchment-dim">
            Works in this world
          </span>
          <span className="font-mono text-[0.65rem] uppercase tracking-widest text-parchment-muted">
            {works.length}
          </span>
        </div>
        {works.length === 0 && (
          <p className="py-8 font-serif italic text-parchment-muted">
            No Works are placed in this world yet.
          </p>
        )}
        <ul>
          {works.map((w) => (
            <li key={w.id} className="border-b border-rule">
              <button
                type="button"
                onClick={() => onOpenWork(w.id)}
                className="flex w-full flex-wrap items-center justify-between gap-3 px-1 py-4 text-left transition-colors hover:bg-ink-700/40"
              >
                <span className="font-serif text-[1.05rem] text-parchment">
                  {w.title}
                </span>
                <span className="flex flex-wrap items-center gap-2">
                  <Pill tone="accent">{DIVISION_LABELS[w.primary_division]}</Pill>
                  {w.primary_medium && <Pill>{MEDIUM_LABELS[w.primary_medium]}</Pill>}
                  <Pill tone={w.canon_status === 'canon' ? 'live' : 'muted'}>
                    {CANON_LABELS[w.canon_status]}
                  </Pill>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      {/* Collaborators (private; cascades to every Work in this world) */}
      <CollaboratorsPanel scope={{ kind: 'world', worldId: world.id }} />
    </div>
  );
}
