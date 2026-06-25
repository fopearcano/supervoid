import { useEffect, useState, type ReactNode } from 'react';
import { fetchWorkCommand } from '@/api/command';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import { iLabel } from '@/types/integrations';
import type { AlertItem, TaskBrief, WorkCommand } from '@/types/command';

type Tone = 'muted' | 'accent' | 'signal' | 'live';
const SEV_TONE: Record<string, Tone> = { critical: 'signal', warning: 'accent', info: 'muted' };

function Facet({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <div className="border border-rule p-4">
      <div className="flex items-center justify-between">
        <Eyebrow>{title}</Eyebrow>
        {count != null && <Pill tone="muted">{count}</Pill>}
      </div>
      <div className="mt-3">{children}</div>
    </div>
  );
}

function Stats({ data }: { data: Record<string, number> }) {
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1.5">
      {Object.entries(data).map(([k, v]) => (
        <span key={k} className="font-mono text-[0.62rem] uppercase tracking-widest text-parchment-muted">
          {iLabel(k)} <span className={`${k === 'blocked' || k === 'overdue' ? (v > 0 ? 'text-signal' : 'text-parchment') : 'text-parchment'}`}>{v}</span>
        </span>
      ))}
    </div>
  );
}

function Items({ items }: { items: AlertItem[] }) {
  if (items.length === 0) return <p className="font-serif italic text-parchment-muted">None.</p>;
  return (
    <ul>
      {items.map((a, i) => (
        <li key={`${a.ref_id ?? a.kind}-${i}`} className="flex items-center justify-between gap-2 border-b border-rule py-1.5">
          <span className="truncate text-sm text-parchment-muted">{a.title}</span>
          <span className="flex shrink-0 items-center gap-2">
            {a.detail && <span className="font-mono text-[0.54rem] uppercase tracking-widest text-parchment-dim">{a.detail}</span>}
            <Pill tone={SEV_TONE[a.severity] ?? 'muted'}>{iLabel(a.kind)}</Pill>
          </span>
        </li>
      ))}
    </ul>
  );
}

function Narrative({ items }: { items: TaskBrief[] }) {
  if (items.length === 0) return <p className="font-serif italic text-parchment-muted">No manuscripts.</p>;
  return (
    <ul>
      {items.map((m) => (
        <li key={m.id} className="flex items-center justify-between gap-2 border-b border-rule py-1.5">
          <span className="truncate text-sm text-parchment-muted">{m.title}</span>
          <Pill tone="muted">{iLabel(m.status)}</Pill>
        </li>
      ))}
    </ul>
  );
}

export function WorkCommandPage({ workId, onBack }: { workId: string; onBack: () => void }) {
  const [cmd, setCmd] = useState<WorkCommand | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setCmd(null);
    fetchWorkCommand(workId)
      .then(setCmd)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load.'));
  }, [workId]);

  if (error) return <p className="font-mono text-[0.7rem] uppercase tracking-widest text-signal">{error}</p>;
  if (!cmd) return <p className="font-mono text-[0.7rem] uppercase tracking-widest text-parchment-dim">Loading…</p>;

  return (
    <div className="flex flex-col gap-8">
      <header>
        <button type="button" onClick={onBack} className="font-mono text-[0.6rem] uppercase tracking-widest text-parchment-dim hover:text-parchment">
          ← Command centre
        </button>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
          <div>
            <Eyebrow>Work command</Eyebrow>
            <h2 className="mt-2 font-serif text-5xl leading-tight text-parchment">{cmd.title}</h2>
            <p className="mt-2 font-mono text-[0.6rem] uppercase tracking-widest text-parchment-dim">
              {iLabel(cmd.division)}{cmd.medium ? ` · ${iLabel(cmd.medium)}` : ''}{cmd.story_world ? ` · ${cmd.story_world}` : ''}
            </p>
          </div>
          <Pill tone="accent">{iLabel(cmd.status)}</Pill>
        </div>
      </header>

      <div className="grid gap-5 lg:grid-cols-2">
        <Facet title="Narrative" count={cmd.narrative.length}><Narrative items={cmd.narrative} /></Facet>
        <Facet title="Production"><Stats data={cmd.production} /></Facet>
        <Facet title="Assets"><Stats data={cmd.assets} /></Facet>
        <Facet title="Collaborators" count={cmd.collaborators.length}><Items items={cmd.collaborators} /></Facet>
        <Facet title="Rights"><Stats data={cmd.rights} /></Facet>
        <Facet title="Editions" count={cmd.editions.length}><Items items={cmd.editions} /></Facet>
        <Facet title="Adaptations" count={cmd.adaptations.length}><Items items={cmd.adaptations} /></Facet>
        <Facet title="Public release">
          {cmd.public_release ? (
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm text-parchment-muted">{cmd.public_release.title}</span>
              <Pill tone={SEV_TONE[cmd.public_release.severity] ?? 'muted'}>{cmd.public_release.detail ?? '—'}</Pill>
            </div>
          ) : (
            <p className="font-serif italic text-parchment-muted">Not published.</p>
          )}
        </Facet>
        <Facet title="Agent history" count={cmd.agent_history.length}><Items items={cmd.agent_history} /></Facet>
      </div>
    </div>
  );
}
