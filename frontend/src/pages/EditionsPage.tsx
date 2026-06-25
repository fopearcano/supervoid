import { useCallback, useEffect, useState } from 'react';
import { ApiError, apiFetch } from '@/api/client';
import {
  createEdition,
  fetchChannels,
  fetchEditionDetail,
  fetchEditions,
  generatePackage,
} from '@/api/business';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import { iLabel } from '@/types/integrations';
import type { Page } from '@/types/manuscript';
import type {
  ChecklistEntry,
  DistributionPackage,
  Edition,
  EditionDetail,
} from '@/types/business';

type Tone = 'muted' | 'accent' | 'signal' | 'live';

const PKG_TONE: Record<string, Tone> = {
  validated: 'live', generated: 'accent', invalid: 'signal', failed: 'signal',
};
const CHECK_TONE: Record<string, Tone> = {
  pass: 'live', warn: 'accent', fail: 'signal', na: 'muted',
};

const FORMATS = [
  'hardcover', 'trade_paperback', 'mass_market', 'pod_paperback', 'ebook',
  'audiobook', 'web_comic', 'pdf', 'box_set', 'other',
];

interface WorkOption {
  id: string;
  title: string;
}

function PackageCard({ pkg }: { pkg: DistributionPackage }) {
  return (
    <div className="border border-rule p-3">
      <div className="flex items-center justify-between">
        <Eyebrow>{iLabel(pkg.channel)}</Eyebrow>
        <Pill tone={PKG_TONE[pkg.status] ?? 'muted'}>{iLabel(pkg.status)}</Pill>
      </div>
      {pkg.validation.errors.length > 0 && (
        <p className="mt-1 font-mono text-[0.62rem] text-signal">
          {pkg.validation.errors.join(' · ')}
        </p>
      )}
      <ul className="mt-2">
        {pkg.checklist.map((c: ChecklistEntry) => (
          <li key={c.key} className="flex items-center justify-between gap-2 py-0.5 text-sm text-parchment-muted">
            <span>{c.label}</span>
            <Pill tone={CHECK_TONE[c.status] ?? 'muted'}>{c.status}</Pill>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EditionPanel({
  editionId,
  channels,
}: {
  editionId: string;
  channels: string[];
}) {
  const [detail, setDetail] = useState<EditionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchEditionDetail(editionId).then(setDetail).catch(() => undefined);
  }, [editionId]);
  useEffect(() => { load(); }, [load]);

  if (!detail) return null;

  return (
    <div className="border border-rule p-4">
      <div className="flex items-center justify-between">
        <span className="font-serif text-[1.1rem] text-parchment">
          {detail.title ?? 'Edition'} · {iLabel(detail.format)}
        </span>
        <Pill tone="accent">{iLabel(detail.distribution_status)}</Pill>
      </div>
      <p className="mt-1 font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
        {detail.identifier ?? 'no identifier'} ({iLabel(detail.identifier_type)}) ·{' '}
        {detail.language}/{detail.territory} · {detail.price ?? '—'} {detail.currency}
      </p>

      <div className="mt-3">
        <Eyebrow>Generate a distribution package</Eyebrow>
        <div className="mt-1 flex flex-wrap gap-2">
          {channels.map((ch) => (
            <button key={ch} type="button" className="button-quiet"
                    onClick={() => generatePackage(editionId, ch)
                      .then(() => { setError(null); load(); })
                      .catch((e) => setError(e instanceof ApiError ? e.message : 'Failed.'))}>
              {iLabel(ch)}
            </button>
          ))}
        </div>
        <p className="mt-1 font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">
          packages are validated and prepared — never uploaded
        </p>
        {error && <p className="mt-1 font-mono text-[0.62rem] text-signal">{error}</p>}
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {detail.packages.map((p) => <PackageCard key={p.id} pkg={p} />)}
      </div>
    </div>
  );
}

export function EditionsPage() {
  const [editions, setEditions] = useState<Edition[]>([]);
  const [channels, setChannels] = useState<string[]>([]);
  const [works, setWorks] = useState<WorkOption[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [workId, setWorkId] = useState('');
  const [format, setFormat] = useState('trade_paperback');
  const [identifier, setIdentifier] = useState('');

  const loadEditions = useCallback(() => {
    fetchEditions().then((p) => setEditions(p.items)).catch(() => undefined);
  }, []);

  useEffect(() => {
    loadEditions();
    fetchChannels().then(setChannels).catch(() => undefined);
    apiFetch<Page<WorkOption>>('/works?limit=100')
      .then((p) => {
        setWorks(p.items);
        if (p.items.length > 0) setWorkId(p.items[0].id);
      })
      .catch(() => undefined);
  }, [loadEditions]);

  const create = () => {
    if (!workId) return;
    createEdition({
      work_id: workId,
      format,
      identifier: identifier.trim() || null,
      identifier_type: identifier.trim() ? 'isbn_13' : 'none',
    }).then(() => { setIdentifier(''); loadEditions(); });
  };

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Eyebrow>Editions & distribution</Eyebrow>
        <h2 className="mt-2 font-serif text-5xl leading-tight text-parchment">Editions</h2>
        <p className="mt-3 max-w-prose text-parchment-muted">
          Concrete editions (format, language, territory, identifier, dimensions, price,
          files, metadata) with validated distribution-package generators for ONIX, KDP,
          Ingram, GlobalComix, press kits and reviewer ARCs.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2 border-b border-rule pb-4">
        <select className="field-select" value={workId} onChange={(e) => setWorkId(e.target.value)}>
          {works.map((w) => <option key={w.id} value={w.id}>{w.title}</option>)}
        </select>
        <select className="field-select" value={format} onChange={(e) => setFormat(e.target.value)}>
          {FORMATS.map((f) => <option key={f} value={f}>{iLabel(f)}</option>)}
        </select>
        <input className="field-input" placeholder="ISBN-13 (optional)"
               value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
        <button type="button" className="button-accent" onClick={create} disabled={!workId}>
          New edition
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ul>
          {editions.map((e) => (
            <li key={e.id} className="border-b border-rule">
              <button type="button" onClick={() => setActiveId(e.id)}
                      className="flex w-full items-center justify-between gap-2 px-1 py-2 text-left text-sm transition-colors hover:bg-ink-700/40">
                <span className="text-parchment-muted">
                  {e.title ?? 'Edition'} · {iLabel(e.format)}
                </span>
                <span className="flex items-center gap-2">
                  <span className="font-mono text-[0.56rem] text-parchment-dim">{e.identifier ?? '—'}</span>
                  <Pill tone="accent">{iLabel(e.distribution_status)}</Pill>
                </span>
              </button>
            </li>
          ))}
          {editions.length === 0 && (
            <li className="py-6 font-serif italic text-parchment-muted">No editions yet.</li>
          )}
        </ul>
        {activeId && <EditionPanel editionId={activeId} channels={channels} />}
      </div>
    </div>
  );
}
