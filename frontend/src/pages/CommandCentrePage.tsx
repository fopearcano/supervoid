import { useEffect, useState, type ReactNode } from 'react';
import {
  fetchAgentInbox,
  fetchAssetHealth,
  fetchBusinessAlerts,
  fetchDivisions,
  fetchMyWork,
  fetchOverview,
} from '@/api/command';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import { iLabel } from '@/types/integrations';
import type {
  AgentInbox,
  AlertItem,
  AssetHealth,
  BusinessAlerts,
  DivisionView,
  Metric,
  MyWork,
  StudioOverview,
  TaskBrief,
} from '@/types/command';

type Tone = 'muted' | 'accent' | 'signal' | 'live';
const SEV_TONE: Record<string, Tone> = { critical: 'signal', warning: 'accent', info: 'muted' };

function sumCounts(counts: Record<string, number>): number {
  return Object.values(counts).reduce((a, b) => a + b, 0);
}

// --- presentational helpers ------------------------------------------------

function StatCell({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="border-l border-rule pl-4">
      <p className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">{label}</p>
      <p className="mt-1 font-serif text-3xl leading-none text-parchment">{value}</p>
      {hint && <p className="mt-1 font-mono text-[0.54rem] uppercase tracking-widest text-parchment-dim/70">{hint}</p>}
    </div>
  );
}

function MetricStrip({ metrics }: { metrics: Metric[] }) {
  const shown = metrics.filter((m) => m.count > 0);
  if (shown.length === 0) return <p className="font-serif italic text-parchment-muted">None.</p>;
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1.5">
      {shown.map((m) => (
        <span key={m.label} className="font-mono text-[0.62rem] uppercase tracking-widest text-parchment-muted">
          {iLabel(m.label)} <span className="text-parchment">{m.count}</span>
        </span>
      ))}
    </div>
  );
}

function AlertList({ items, onOpenWork }: { items: AlertItem[]; onOpenWork?: (id: string) => void }) {
  if (items.length === 0) return <p className="py-2 font-serif italic text-parchment-muted">Nothing here.</p>;
  return (
    <ul>
      {items.map((a, i) => (
        <li key={`${a.ref_id ?? a.kind}-${i}`} className="flex flex-col gap-1 border-b border-rule py-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
          <span className="min-w-0">
            <button
              type="button"
              disabled={!a.work_id || !onOpenWork}
              onClick={() => a.work_id && onOpenWork?.(a.work_id)}
              className={`block truncate text-left text-sm ${a.work_id && onOpenWork ? 'text-parchment-muted hover:text-parchment' : 'text-parchment-muted'}`}
            >
              {a.title}
            </button>
            {a.detail && <span className="block truncate font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">{a.detail}</span>}
          </span>
          <span className="flex shrink-0 items-center gap-2">
            {a.due_date && (
              <span className="font-mono text-[0.56rem] text-parchment-dim">
                {a.due_date}{a.days_remaining != null ? ` · ${a.days_remaining}d` : ''}
              </span>
            )}
            <Pill tone={SEV_TONE[a.severity] ?? 'muted'}>{iLabel(a.kind)}</Pill>
          </span>
        </li>
      ))}
    </ul>
  );
}

function TaskList({ tasks, onOpenWork }: { tasks: TaskBrief[]; onOpenWork?: (id: string) => void }) {
  if (tasks.length === 0) return <p className="py-2 font-serif italic text-parchment-muted">Nothing here.</p>;
  return (
    <ul>
      {tasks.map((t) => (
        <li key={t.id} className="flex flex-col gap-1 border-b border-rule py-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
          <button
            type="button"
            disabled={!t.work_id || !onOpenWork}
            onClick={() => t.work_id && onOpenWork?.(t.work_id)}
            className="block min-w-0 truncate text-left text-sm text-parchment-muted hover:text-parchment"
          >
            {t.title ?? 'Untitled task'}
          </button>
          <span className="flex shrink-0 items-center gap-2">
            {t.due_date && (
              <span className={`font-mono text-[0.56rem] ${t.days_until != null && t.days_until < 0 ? 'text-signal' : 'text-parchment-dim'}`}>
                {t.due_date}
              </span>
            )}
            <Pill tone="muted">{iLabel(t.status)}</Pill>
          </span>
        </li>
      ))}
    </ul>
  );
}

function Section({
  eyebrow, title, badge, badgeTone = 'accent', open, onToggle, children,
}: {
  eyebrow: string; title: string; badge?: number; badgeTone?: Tone;
  open: boolean; onToggle: () => void; children: ReactNode;
}) {
  return (
    <section className="border-t border-rule pt-6">
      <button type="button" onClick={onToggle} className="flex w-full items-center justify-between text-left">
        <span>
          <Eyebrow>{eyebrow}</Eyebrow>
          <span className="mt-1 block font-serif text-2xl text-parchment">{title}</span>
        </span>
        <span className="flex items-center gap-3">
          {badge != null && badge > 0 && <Pill tone={badgeTone}>{badge}</Pill>}
          <span className="font-mono text-lg text-parchment-dim">{open ? '–' : '+'}</span>
        </span>
      </button>
      {open && <div className="mt-6">{children}</div>}
    </section>
  );
}

function SubGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-5">
      <Eyebrow>{title}</Eyebrow>
      <div className="mt-2">{children}</div>
    </div>
  );
}

// --- page ------------------------------------------------------------------

export function CommandCentrePage({ onOpenWork }: { onOpenWork: (workId: string) => void }) {
  const [overview, setOverview] = useState<StudioOverview | null>(null);
  const [myWork, setMyWork] = useState<MyWork | null>(null);
  const [inbox, setInbox] = useState<AgentInbox | null>(null);
  const [health, setHealth] = useState<AssetHealth | null>(null);
  const [alerts, setAlerts] = useState<BusinessAlerts | null>(null);
  const [divisions, setDivisions] = useState<DivisionView[] | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({
    'my-work': true, 'business': true,
  });
  const toggle = (k: string) => setOpen((o) => ({ ...o, [k]: !o[k] }));

  useEffect(() => {
    fetchOverview().then(setOverview).catch(() => undefined);
    fetchMyWork().then(setMyWork).catch(() => undefined);
    fetchAgentInbox().then(setInbox).catch(() => undefined);
    fetchAssetHealth().then(setHealth).catch(() => undefined);
    fetchBusinessAlerts().then(setAlerts).catch(() => undefined);
  }, []);

  // Divisions load lazily on first expand.
  useEffect(() => {
    if (open['divisions'] && divisions === null) {
      fetchDivisions().then(setDivisions).catch(() => setDivisions([]));
    }
  }, [open, divisions]);

  const gn = overview?.graphic_novel;

  return (
    <div className="flex flex-col gap-10">
      {/* Hero / studio overview (always visible) */}
      <section>
        <Eyebrow>Command · SUPERVOID studio</Eyebrow>
        <h2 className="mt-3 font-serif text-5xl leading-tight text-parchment">
          The studio at a glance.
        </h2>
        <p className="mt-4 max-w-prose text-parchment-muted">
          One archival surface over the whole house — story worlds, works and divisions; your
          desk; the agents; asset health; and the business calendar. Open a section when you need
          it; everything else stays out of the way.
        </p>

        <div className="mt-8 grid grid-cols-2 gap-y-6 sm:grid-cols-3 lg:grid-cols-6">
          <StatCell label="Story worlds" value={overview?.story_worlds ?? '—'} />
          <StatCell label="Active works" value={overview?.active_works ?? '—'} hint={overview ? `${overview.works_total} total` : undefined} />
          <StatCell label="GN complete" value={gn ? `${gn.completion_pct}%` : '—'} hint={gn ? `${gn.pages_complete}/${gn.pages_total} pp` : undefined} />
          <StatCell label="Releases" value={overview?.releases_upcoming ?? '—'} hint="upcoming" />
          <StatCell label="Open findings" value={inbox?.open_findings ?? '—'} />
          <StatCell label="Alerts" value={alerts ? sumCounts(alerts.counts) : '—'} />
        </div>
      </section>

      {/* 1. Studio overview detail */}
      <Section eyebrow="Studio" title="Overview" open={!!open['overview']} onToggle={() => toggle('overview')}>
        {overview && (
          <div className="grid gap-6 lg:grid-cols-2">
            <div>
              <SubGroup title="Divisions"><MetricStrip metrics={overview.divisions} /></SubGroup>
              <SubGroup title="Works by status"><MetricStrip metrics={overview.works_by_status} /></SubGroup>
              <SubGroup title="Screen production"><MetricStrip metrics={overview.screen_by_status} /></SubGroup>
              <SubGroup title="Adaptation dossiers"><MetricStrip metrics={overview.adaptation_dossiers} /></SubGroup>
            </div>
            <SubGroup title="Releases"><AlertList items={overview.releases} onOpenWork={onOpenWork} /></SubGroup>
          </div>
        )}
      </Section>

      {/* 2. My work */}
      <Section eyebrow="Your desk" title="My work" badge={myWork ? sumCounts(myWork.counts) : undefined}
        open={!!open['my-work']} onToggle={() => toggle('my-work')}>
        {myWork && (
          <div className="grid gap-6 lg:grid-cols-2">
            <SubGroup title={`Assigned · ${myWork.counts.assigned ?? 0}`}><TaskList tasks={myWork.assigned} onOpenWork={onOpenWork} /></SubGroup>
            <SubGroup title={`Overdue · ${myWork.counts.overdue ?? 0}`}><TaskList tasks={myWork.overdue} onOpenWork={onOpenWork} /></SubGroup>
            <SubGroup title={`Blocked · ${myWork.counts.blocked ?? 0}`}><TaskList tasks={myWork.blocked} onOpenWork={onOpenWork} /></SubGroup>
            <SubGroup title={`Requested reviews · ${myWork.counts.requested_reviews ?? 0}`}><TaskList tasks={myWork.requested_reviews} onOpenWork={onOpenWork} /></SubGroup>
            <SubGroup title={`Approval queue · ${myWork.counts.approval_queue ?? 0}`}><AlertList items={myWork.approval_queue} /></SubGroup>
          </div>
        )}
      </Section>

      {/* 3. Agent inbox */}
      <Section eyebrow="Studio agents" title="Agent inbox"
        badge={inbox ? inbox.open_findings + inbox.pending_proposals.length + inbox.failed_runs.length : undefined}
        badgeTone={inbox && inbox.failed_runs.length ? 'signal' : 'accent'}
        open={!!open['agents']} onToggle={() => toggle('agents')}>
        {inbox && (
          <div className="grid gap-6 lg:grid-cols-2">
            <SubGroup title="Findings by severity"><MetricStrip metrics={inbox.findings_by_severity} /></SubGroup>
            <SubGroup title="Pending proposals"><AlertList items={inbox.pending_proposals} onOpenWork={onOpenWork} /></SubGroup>
            <SubGroup title="Failed runs"><AlertList items={inbox.failed_runs} onOpenWork={onOpenWork} /></SubGroup>
            <SubGroup title="Recently completed"><AlertList items={inbox.recent_completed} onOpenWork={onOpenWork} /></SubGroup>
          </div>
        )}
      </Section>

      {/* 4. Asset health */}
      <Section eyebrow="Provenance" title="Asset health" badge={health ? sumCounts(health.counts) : undefined}
        open={!!open['assets']} onToggle={() => toggle('assets')}>
        {health && (
          <div className="grid gap-6 lg:grid-cols-2">
            <SubGroup title={`Missing files · ${health.counts.missing_files}`}><AlertList items={health.missing_files} /></SubGroup>
            <SubGroup title={`Incomplete provenance · ${health.counts.incomplete_provenance}`}><AlertList items={health.incomplete_provenance} /></SubGroup>
            <SubGroup title={`Expiring licences · ${health.counts.expiring_licences}`}><AlertList items={health.expiring_licences} /></SubGroup>
            <SubGroup title={`Unapproved versions · ${health.counts.unapproved_versions}`}><AlertList items={health.unapproved_versions} /></SubGroup>
            <SubGroup title={`Public assets without credits · ${health.counts.public_without_credits}`}><AlertList items={health.public_without_credits} /></SubGroup>
          </div>
        )}
      </Section>

      {/* 5. Business alerts */}
      <Section eyebrow="The business" title="Business alerts" badge={alerts ? sumCounts(alerts.counts) : undefined}
        open={!!open['business']} onToggle={() => toggle('business')}>
        {alerts && (
          <div className="grid gap-6 lg:grid-cols-2">
            <SubGroup title={`Rights expiries · ${alerts.counts.rights_expiries}`}><AlertList items={alerts.rights_expiries} onOpenWork={onOpenWork} /></SubGroup>
            <SubGroup title={`Contract deadlines · ${alerts.counts.contract_deadlines}`}><AlertList items={alerts.contract_deadlines} onOpenWork={onOpenWork} /></SubGroup>
            <SubGroup title={`Distribution readiness · ${alerts.counts.distribution_readiness}`}><AlertList items={alerts.distribution_readiness} onOpenWork={onOpenWork} /></SubGroup>
            <SubGroup title={`Contact follow-ups · ${alerts.counts.contact_follow_ups}`}><AlertList items={alerts.contact_follow_ups} /></SubGroup>
            <SubGroup title={`Upcoming releases · ${alerts.counts.upcoming_releases}`}><AlertList items={alerts.upcoming_releases} onOpenWork={onOpenWork} /></SubGroup>
          </div>
        )}
      </Section>

      {/* 6. Division views */}
      <Section eyebrow="Divisions" title="Publishing · Pictures · Interactive · Cross-media"
        open={!!open['divisions']} onToggle={() => toggle('divisions')}>
        <div className="grid gap-6 lg:grid-cols-2">
          {(divisions ?? []).map((d) => (
            <div key={d.division} className="border border-rule p-4">
              <div className="flex items-center justify-between">
                <span className="font-serif text-[1.1rem] text-parchment">{iLabel(d.division)}</span>
                <Pill tone="muted">{d.works_count} works</Pill>
              </div>
              <div className="mt-2"><MetricStrip metrics={d.metrics} /></div>
              <ul className="mt-3">
                {d.works.map((w) => (
                  <li key={w.id} className="border-b border-rule">
                    <button type="button" onClick={() => onOpenWork(w.id)}
                      className="flex w-full items-center justify-between gap-2 px-1 py-1.5 text-left text-sm transition-colors hover:bg-ink-700/40">
                      <span className="min-w-0 truncate text-parchment-muted">{w.title}</span>
                      <Pill tone="muted">{iLabel(w.status)}</Pill>
                    </button>
                  </li>
                ))}
                {d.works.length === 0 && <li className="py-2 font-serif italic text-parchment-muted">No works.</li>}
              </ul>
            </div>
          ))}
          {divisions === null && <p className="font-mono text-[0.7rem] uppercase tracking-widest text-parchment-dim">Loading…</p>}
        </div>
      </Section>
    </div>
  );
}
