import { useEffect, useState } from 'react';
import { ApiError } from '@/api/client';
import {
  createAdaptationDossier,
  fetchAdaptationDossiers,
  fetchWorks,
} from '@/api/transmedia';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import {
  ADAPTATION_STATUSES,
  ADAPTATION_STATUS_LABELS,
  DIVISIONS,
  DIVISION_LABELS,
  MEDIA,
  MEDIUM_LABELS,
  RIGHTS_CLEARANCE_LABELS,
  type AdaptationDossier,
  type AdaptationStatus,
  type Medium,
  type StudioDivision,
  type TransmediaWork,
} from '@/types/transmedia';

interface Props {
  onOpenWork: (id: string) => void;
}

export function AdaptationDossiersPage({ onOpenWork }: Props) {
  const [dossiers, setDossiers] = useState<AdaptationDossier[] | null>(null);
  const [works, setWorks] = useState<TransmediaWork[]>([]);
  const [filter, setFilter] = useState<AdaptationStatus | ''>('');
  const [error, setError] = useState<string | null>(null);

  const [sourceId, setSourceId] = useState('');
  const [medium, setMedium] = useState<Medium>('film');
  const [division, setDivision] = useState<StudioDivision>('pictures');
  const [logline, setLogline] = useState('');
  const [busy, setBusy] = useState(false);

  const load = () => {
    fetchAdaptationDossiers(filter ? { status: filter } : {})
      .then((p) => setDossiers(p.items))
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : 'Failed to load dossiers.'),
      );
  };

  useEffect(load, [filter]);
  useEffect(() => {
    fetchWorks().then((p) => setWorks(p.items)).catch(() => undefined);
  }, []);

  const submit = async () => {
    if (!sourceId) return;
    setBusy(true);
    setError(null);
    try {
      await createAdaptationDossier({
        source_work_id: sourceId,
        target_medium: medium,
        target_division: division,
        logline: logline.trim() || null,
      });
      setSourceId('');
      setLogline('');
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to create dossier.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-14">
      <header>
        <Eyebrow>Studio · transmedia development</Eyebrow>
        <h2 className="mt-3 font-serif text-5xl leading-tight text-parchment">
          Adaptation Dossiers
        </h2>
        <p className="mt-4 max-w-prose text-parchment-muted">
          The development seam between divisions. Each dossier tracks adapting a
          source Work into another medium — a graphic novel into a film, a book
          into an audio drama — through to a linked target Work.
        </p>
      </header>

      {/* Create */}
      <section className="border border-rule p-6">
        <Eyebrow>New dossier</Eyebrow>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <select
            className="field-select"
            value={sourceId}
            onChange={(e) => setSourceId(e.target.value)}
            aria-label="Source work"
          >
            <option value="">Source Work…</option>
            {works.map((w) => (
              <option key={w.id} value={w.id}>
                {w.title}
              </option>
            ))}
          </select>
          <select
            className="field-select"
            value={medium}
            onChange={(e) => setMedium(e.target.value as Medium)}
            aria-label="Target medium"
          >
            {MEDIA.map((m) => (
              <option key={m} value={m}>
                {MEDIUM_LABELS[m]}
              </option>
            ))}
          </select>
          <select
            className="field-select"
            value={division}
            onChange={(e) => setDivision(e.target.value as StudioDivision)}
            aria-label="Target division"
          >
            {DIVISIONS.map((d) => (
              <option key={d} value={d}>
                {DIVISION_LABELS[d]}
              </option>
            ))}
          </select>
        </div>
        <input
          className="field-input mt-3 w-full"
          placeholder="Logline (optional)"
          value={logline}
          onChange={(e) => setLogline(e.target.value)}
        />
        <div className="mt-4 flex items-center gap-4">
          <button
            type="button"
            className="button-accent"
            onClick={submit}
            disabled={busy || !sourceId}
          >
            Open dossier
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
        <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-rule pb-3">
          <span className="font-mono text-[0.65rem] uppercase tracking-widest text-parchment-dim">
            Dossiers
          </span>
          <select
            className="field-mono"
            value={filter}
            onChange={(e) => setFilter(e.target.value as AdaptationStatus | '')}
            aria-label="Filter by status"
          >
            <option value="">All statuses</option>
            {ADAPTATION_STATUSES.map((s) => (
              <option key={s} value={s}>
                {ADAPTATION_STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </div>

        {dossiers !== null && dossiers.length === 0 && (
          <p className="py-12 font-serif italic text-parchment-muted">
            No adaptation dossiers{filter ? ' with this status' : ''} yet.
          </p>
        )}

        {dossiers !== null && dossiers.length > 0 && (
          <ul className="border-b border-rule">
            {dossiers.map((d) => (
              <li key={d.id} className="border-t border-rule py-5">
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <button
                    type="button"
                    onClick={() => onOpenWork(d.source_work_id)}
                    className="text-left font-serif text-[1.1rem] text-parchment hover:text-accent"
                  >
                    {d.source_work_title ?? 'Source'}
                    <span className="px-2 text-parchment-dim">→</span>
                    <span className="text-parchment-muted">
                      {d.target_work_title ?? MEDIUM_LABELS[d.target_medium]}
                    </span>
                  </button>
                  <span className="flex flex-wrap items-center gap-2">
                    <Pill tone="accent">{DIVISION_LABELS[d.target_division]}</Pill>
                    <Pill>{MEDIUM_LABELS[d.target_medium]}</Pill>
                    <Pill tone={d.status === 'released' ? 'live' : 'muted'}>
                      {ADAPTATION_STATUS_LABELS[d.status]}
                    </Pill>
                  </span>
                </div>
                {d.logline && (
                  <p className="mt-2 max-w-prose text-sm text-parchment-muted/80">
                    {d.logline}
                  </p>
                )}
                <div className="mt-2 font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
                  Rights: {RIGHTS_CLEARANCE_LABELS[d.rights_clearance]}
                  {d.format ? ` · ${d.format}` : ''}
                  {d.intended_scope ? ` · ${d.intended_scope}` : ''}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
