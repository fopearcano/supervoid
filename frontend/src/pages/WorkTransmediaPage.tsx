import { useEffect, useState } from 'react';
import { ApiError } from '@/api/client';
import { fetchWorkTransmedia } from '@/api/transmedia';
import { CollaboratorsPanel } from '@/components/CollaboratorsPanel';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import {
  ADAPTATION_STATUS_LABELS,
  CANON_LABELS,
  DIVISION_LABELS,
  MEDIUM_LABELS,
  type TransmediaWork,
  type WorkTransmediaOverview,
} from '@/types/transmedia';

interface Props {
  workId: string;
  onBack: () => void;
  onOpenWork: (id: string) => void;
}

function WorkLine({
  work,
  onOpen,
}: {
  work: TransmediaWork;
  onOpen?: () => void;
}) {
  const inner = (
    <span className="flex flex-wrap items-center justify-between gap-3">
      <span className="font-serif text-[1.05rem] text-parchment">{work.title}</span>
      <span className="flex flex-wrap items-center gap-2">
        <Pill tone="accent">{DIVISION_LABELS[work.primary_division]}</Pill>
        {work.primary_medium && <Pill>{MEDIUM_LABELS[work.primary_medium]}</Pill>}
        <Pill tone={work.canon_status === 'canon' ? 'live' : 'muted'}>
          {CANON_LABELS[work.canon_status]}
        </Pill>
      </span>
    </span>
  );
  return onOpen ? (
    <button
      type="button"
      onClick={onOpen}
      className="block w-full border-b border-rule py-4 text-left transition-colors hover:bg-ink-700/40"
    >
      {inner}
    </button>
  ) : (
    <div className="border-b border-rule py-4">{inner}</div>
  );
}

export function WorkTransmediaPage({ workId, onBack, onOpenWork }: Props) {
  const [data, setData] = useState<WorkTransmediaOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchWorkTransmedia(workId)
      .then((d) => !cancelled && setData(d))
      .catch((e) =>
        !cancelled &&
        setError(e instanceof ApiError ? e.message : 'Failed to load overview.'),
      );
    return () => {
      cancelled = true;
    };
  }, [workId]);

  if (error) {
    return (
      <p className="font-mono text-[0.7rem] uppercase tracking-widest text-signal">
        {error}
      </p>
    );
  }
  if (!data) {
    return (
      <p className="font-mono text-[0.7rem] uppercase tracking-widest text-parchment-dim">
        Loading…
      </p>
    );
  }

  const { work, story_world, story_series, source_work, derived_works, adaptation_dossiers } =
    data;

  return (
    <div className="flex flex-col gap-14">
      <header>
        <button
          type="button"
          onClick={onBack}
          className="font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim hover:text-parchment"
        >
          ← Back
        </button>
        <Eyebrow>Work · transmedia overview</Eyebrow>
        <h2 className="mt-2 font-serif text-5xl leading-tight text-parchment">
          {work.title}
        </h2>
        {work.subtitle && (
          <p className="mt-2 font-serif text-xl italic text-parchment-dim">
            {work.subtitle}
          </p>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Pill tone="accent">{DIVISION_LABELS[work.primary_division]}</Pill>
          {work.primary_medium && <Pill>{MEDIUM_LABELS[work.primary_medium]}</Pill>}
          <Pill tone={work.canon_status === 'canon' ? 'live' : 'muted'}>
            {CANON_LABELS[work.canon_status]}
          </Pill>
        </div>
      </header>

      {/* IP placement */}
      <section className="grid gap-8 sm:grid-cols-2">
        <div>
          <Eyebrow>Story world</Eyebrow>
          {story_world ? (
            <p className="mt-2 font-serif text-lg text-parchment">{story_world.name}</p>
          ) : (
            <p className="mt-2 font-serif italic text-parchment-muted">Unassigned</p>
          )}
        </div>
        <div>
          <Eyebrow>Series</Eyebrow>
          {story_series ? (
            <p className="mt-2 font-serif text-lg text-parchment">
              {story_series.title}
              <span className="ml-2 font-mono text-[0.58rem] uppercase tracking-widest text-parchment-shadow">
                #{story_series.sequence_order}
              </span>
            </p>
          ) : (
            <p className="mt-2 font-serif italic text-parchment-muted">None</p>
          )}
        </div>
      </section>

      {/* Source */}
      {source_work && (
        <section>
          <Eyebrow>Adapted from</Eyebrow>
          <div className="mt-3 border-t border-rule">
            <WorkLine work={source_work} onOpen={() => onOpenWork(source_work.id)} />
          </div>
        </section>
      )}

      {/* Derived works */}
      <section>
        <div className="flex items-baseline justify-between border-b border-rule pb-3">
          <span className="font-mono text-[0.65rem] uppercase tracking-widest text-parchment-dim">
            Derived works
          </span>
          <span className="font-mono text-[0.65rem] uppercase tracking-widest text-parchment-muted">
            {derived_works.length}
          </span>
        </div>
        {derived_works.length === 0 ? (
          <p className="py-6 font-serif italic text-parchment-muted">
            No Works derived from this one yet.
          </p>
        ) : (
          derived_works.map((w) => (
            <WorkLine key={w.id} work={w} onOpen={() => onOpenWork(w.id)} />
          ))
        )}
      </section>

      {/* Adaptation dossiers (this work as source) */}
      <section>
        <div className="flex items-baseline justify-between border-b border-rule pb-3">
          <span className="font-mono text-[0.65rem] uppercase tracking-widest text-parchment-dim">
            Adaptation dossiers
          </span>
          <span className="font-mono text-[0.65rem] uppercase tracking-widest text-parchment-muted">
            {adaptation_dossiers.length}
          </span>
        </div>
        {adaptation_dossiers.length === 0 ? (
          <p className="py-6 font-serif italic text-parchment-muted">
            No adaptations in development from this Work.
          </p>
        ) : (
          <ul>
            {adaptation_dossiers.map((d) => (
              <li
                key={d.id}
                className="flex flex-wrap items-center justify-between gap-3 border-b border-rule py-4"
              >
                <span className="text-parchment-muted">
                  → {d.target_work_title ?? MEDIUM_LABELS[d.target_medium]}
                  {d.logline && (
                    <span className="ml-2 text-sm text-parchment-muted/70">
                      {d.logline}
                    </span>
                  )}
                </span>
                <span className="flex flex-wrap items-center gap-2">
                  <Pill tone="accent">{DIVISION_LABELS[d.target_division]}</Pill>
                  <Pill>{MEDIUM_LABELS[d.target_medium]}</Pill>
                  <Pill tone={d.status === 'released' ? 'live' : 'muted'}>
                    {ADAPTATION_STATUS_LABELS[d.status]}
                  </Pill>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Collaborators (private; this Work, plus any inherited from its world) */}
      <CollaboratorsPanel
        scope={{ kind: 'work', workId: work.id, storyWorldId: work.story_world_id }}
      />
    </div>
  );
}
