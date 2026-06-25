import { useCallback, useEffect, useState, type ReactNode } from 'react';
import {
  fetchRights,
  fetchRightsDetail,
  fetchRightsWarnings,
} from '@/api/business';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import { iLabel } from '@/types/integrations';
import type {
  RightsDetail,
  RightsProfile,
  RightsWarning,
} from '@/types/business';

type View = 'profiles' | 'warnings';
type Tone = 'muted' | 'accent' | 'signal' | 'live';

const RIGHT_TONE: Record<string, Tone> = {
  licensed: 'live', sold: 'live', optioned: 'accent', reserved: 'accent',
  available: 'muted', not_applicable: 'muted',
};
const WARN_TONE: Record<string, Tone> = {
  overdue: 'signal', due_soon: 'accent', upcoming: 'muted',
};

function tone(map: Record<string, Tone>, k: string): Tone {
  return map[k] ?? 'muted';
}

const SCOPES: { key: keyof RightsProfile; label: string }[] = [
  { key: 'print_rights', label: 'Print' },
  { key: 'ebook_rights', label: 'Ebook' },
  { key: 'audiobook_rights', label: 'Audio' },
  { key: 'film_rights', label: 'Film' },
  { key: 'adaptation_rights', label: 'Adaptation' },
  { key: 'merchandising_rights', label: 'Merch' },
];

function Detail({ detail }: { detail: RightsDetail }) {
  return (
    <div className="border border-rule p-4">
      <div className="flex items-center justify-between">
        <span className="font-serif text-[1.1rem] text-parchment">
          {detail.territory} · {detail.language}
        </span>
        <Pill tone="accent">{iLabel(detail.exclusivity)}</Pill>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {SCOPES.map((s) => (
          <Pill key={s.key} tone={tone(RIGHT_TONE, String(detail[s.key]))}>
            {s.label}: {iLabel(String(detail[s.key]))}
          </Pill>
        ))}
      </div>
      <p className="mt-2 font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
        holder {detail.rights_holder ?? detail.holder ?? '—'} · sublicensable{' '}
        {detail.sublicensable ? 'yes' : 'no'} · term {detail.term_start_date ?? '—'} →{' '}
        {detail.term_end_date ?? '—'}
      </p>
      {detail.reversion_conditions && (
        <p className="mt-1 text-sm text-parchment-muted">
          Reversion: {detail.reversion_conditions}
        </p>
      )}

      {detail.windows.length > 0 && (
        <Section title="Term windows">
          {detail.windows.map((w) => (
            <Row key={w.id} left={`${iLabel(w.scope)} · ${w.territory}/${w.language}`}
                 right={`${w.starts_on ?? '—'} → ${w.ends_on ?? '—'} (${iLabel(w.status)})`} />
          ))}
        </Section>
      )}
      {detail.options.length > 0 && (
        <Section title="Option periods">
          {detail.options.map((o) => (
            <Row key={o.id} left={`${o.label} (${iLabel(o.scope)})`}
                 right={`deadline ${o.exercise_deadline ?? o.option_end ?? '—'} · ${iLabel(o.status)}`} />
          ))}
        </Section>
      )}
      {detail.chain_of_title.length > 0 && (
        <Section title="Chain of title">
          {detail.chain_of_title.map((c) => (
            <Row key={c.id} left={`${iLabel(c.entry_type)}: ${c.from_party ?? '?'} → ${c.to_party ?? '?'}`}
                 right={c.effective_date ?? ''} />
          ))}
        </Section>
      )}
      {detail.evidence.length > 0 && (
        <Section title="Evidence">
          {detail.evidence.map((e) => (
            <Row key={e.id} left={`${iLabel(e.kind)}: ${e.title}`} right={e.document_ref ?? ''} />
          ))}
        </Section>
      )}
      {detail.status_history.length > 0 && (
        <Section title="Status history">
          {detail.status_history.map((h) => (
            <Row key={h.id} left={`${iLabel(h.scope)}: ${iLabel(h.from_status ?? '—')} → ${iLabel(h.to_status)}`}
                 right={h.changed_at.slice(0, 10)} />
          ))}
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mt-3">
      <Eyebrow>{title}</Eyebrow>
      <ul className="mt-1">{children}</ul>
    </div>
  );
}

function Row({ left, right }: { left: string; right: string }) {
  return (
    <li className="flex items-center justify-between gap-2 border-b border-rule py-1 text-sm text-parchment-muted">
      <span>{left}</span>
      <span className="font-mono text-[0.56rem] text-parchment-dim">{right}</span>
    </li>
  );
}

export function RightsDeskPage() {
  const [view, setView] = useState<View>('profiles');
  const [profiles, setProfiles] = useState<RightsProfile[]>([]);
  const [detail, setDetail] = useState<RightsDetail | null>(null);
  const [warnings, setWarnings] = useState<RightsWarning[]>([]);

  useEffect(() => {
    fetchRights().then((p) => setProfiles(p.items)).catch(() => undefined);
  }, []);

  const loadWarnings = useCallback(() => {
    fetchRightsWarnings().then(setWarnings).catch(() => undefined);
  }, []);
  useEffect(() => {
    if (view === 'warnings') loadWarnings();
  }, [view, loadWarnings]);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Eyebrow>Rights desk</Eyebrow>
        <h2 className="mt-2 font-serif text-5xl leading-tight text-parchment">Rights</h2>
        <p className="mt-3 max-w-prose text-parchment-muted">
          Term windows, exclusivity, options, chain of title, evidence and status
          history per rights profile — with reminders and expiry warnings.
        </p>
      </header>

      <div className="flex items-center gap-2 border-b border-rule pb-3">
        {(['profiles', 'warnings'] as View[]).map((v) => (
          <button key={v} type="button" onClick={() => setView(v)}
                  className={`nav-link ${view === v ? 'nav-link-active' : ''}`}>
            {iLabel(v)}
          </button>
        ))}
      </div>

      {view === 'profiles' && (
        <div className="grid gap-6 lg:grid-cols-2">
          <ul>
            {profiles.map((p) => (
              <li key={p.id} className="border-b border-rule">
                <button type="button"
                        onClick={() => fetchRightsDetail(p.id).then(setDetail)}
                        className="flex w-full items-center justify-between gap-2 px-1 py-2 text-left text-sm transition-colors hover:bg-ink-700/40">
                  <span className="text-parchment-muted">{p.territory} · {p.language}</span>
                  <Pill tone="accent">{iLabel(p.exclusivity)}</Pill>
                </button>
              </li>
            ))}
            {profiles.length === 0 && (
              <li className="py-6 font-serif italic text-parchment-muted">No rights profiles.</li>
            )}
          </ul>
          {detail && <Detail detail={detail} />}
        </div>
      )}

      {view === 'warnings' && (
        <ul>
          {warnings.map((w, i) => (
            <li key={`${w.source_id}-${i}`}
                className="flex flex-wrap items-center justify-between gap-3 border-b border-rule py-3">
              <span className="flex items-center gap-2">
                <Pill tone={tone(WARN_TONE, w.status)}>{iLabel(w.status)}</Pill>
                <span className="text-parchment-muted">{w.message}</span>
                <span className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">
                  {iLabel(w.kind)} · {w.source}
                </span>
              </span>
              <span className="font-mono text-[0.62rem] text-parchment-dim">
                {w.due_date} ({w.days_remaining}d)
              </span>
            </li>
          ))}
          {warnings.length === 0 && (
            <li className="py-6 font-serif italic text-parchment-muted">No upcoming reminders.</li>
          )}
        </ul>
      )}
    </div>
  );
}
