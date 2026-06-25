import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError } from '@/api/client';
import {
  approveRun,
  executeRun,
  fetchAdapters,
  fetchLinks,
  fetchPointConfig,
  fetchPointHealth,
  fetchPoints,
  fetchRuns,
  rejectRun,
  requestOperation,
} from '@/api/integrations';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import {
  iLabel,
  type AdapterHealth,
  type ConfigStatus,
  type IntegrationAdapter,
  type IntegrationLink,
  type IntegrationPoint,
  type IntegrationRun,
} from '@/types/integrations';

type View = 'adapters' | 'points' | 'runs' | 'links';
type Tone = 'muted' | 'accent' | 'signal' | 'live';

const RUN_TONE: Record<string, Tone> = {
  succeeded: 'live', approved: 'live', running: 'accent', pending_approval: 'accent',
  failed: 'signal', rejected: 'signal', cancelled: 'muted',
};
const HEALTH_TONE: Record<string, Tone> = {
  healthy: 'live', unknown: 'accent', degraded: 'accent',
  unreachable: 'signal', not_configured: 'signal', disabled: 'muted',
};
const RISK_TONE: Record<string, Tone> = {
  critical: 'signal', high: 'signal', medium: 'accent', low: 'muted',
};

function tone(map: Record<string, Tone>, key: string): Tone {
  return map[key] ?? 'muted';
}

function opTone(op: { external: boolean; mutating: boolean }): Tone {
  if (op.external) return 'signal';
  if (op.mutating) return 'accent';
  return 'muted';
}

// --- run card --------------------------------------------------------------

function RunCard({ run, onChanged }: { run: IntegrationRun; onChanged: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const act = (fn: () => Promise<unknown>) =>
    fn().then(() => { setError(null); onChanged(); })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Action failed.'));

  return (
    <div className="border border-rule p-4">
      <div className="flex items-center justify-between gap-2">
        <Eyebrow>{run.adapter_key} · {iLabel(run.operation)}</Eyebrow>
        <span className="flex items-center gap-1.5">
          {run.dry_run && <Pill tone="muted">dry-run</Pill>}
          {run.is_external && <Pill tone="signal">external</Pill>}
          <Pill tone={tone(RUN_TONE, run.status)}>{iLabel(run.status)}</Pill>
        </span>
      </div>
      <p className="mt-2 font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
        {run.direction} · {run.correlation_id?.slice(0, 8) ?? '—'}
        {run.requested_by_name ? ` · by ${run.requested_by_name}` : ''}
      </p>
      {run.error && <p className="mt-2 font-mono text-[0.62rem] text-signal">{run.error}</p>}
      {Object.keys(run.output).length > 0 && (
        <pre className="mt-2 max-h-48 overflow-auto border border-rule bg-ink-900/40 p-2 font-mono text-[0.6rem] text-parchment-muted">
          {JSON.stringify(run.output, null, 2)}
        </pre>
      )}
      {run.status === 'pending_approval' && (
        <div className="mt-3 flex items-center gap-2">
          <button type="button" className="button-accent" onClick={() => act(() => approveRun(run.id))}>Approve</button>
          <button type="button" className="button-quiet" onClick={() => act(() => rejectRun(run.id))}>Reject</button>
        </div>
      )}
      {run.status === 'approved' && (
        <div className="mt-3">
          <button type="button" className="button-accent" onClick={() => act(() => executeRun(run.id))}>Execute</button>
        </div>
      )}
      {error && <p className="mt-2 font-mono text-[0.62rem] text-signal">{error}</p>}
    </div>
  );
}

// --- point operations panel ------------------------------------------------

function PointPanel({
  point,
  adapter,
  onRan,
}: {
  point: IntegrationPoint;
  adapter: IntegrationAdapter | undefined;
  onRan: () => void;
}) {
  const [health, setHealth] = useState<AdapterHealth | null>(null);
  const [config, setConfig] = useState<ConfigStatus | null>(null);
  const [operation, setOperation] = useState('');
  const [payload, setPayload] = useState('{}');
  const [dryRun, setDryRun] = useState(true);
  const [run, setRun] = useState<IntegrationRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRun(null);
    setError(null);
    fetchPointHealth(point.id).then(setHealth).catch(() => setHealth(null));
    fetchPointConfig(point.id).then(setConfig).catch(() => setConfig(null));
    setOperation(adapter?.operations[0]?.key ?? '');
  }, [point.id, adapter]);

  const doRun = () => {
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(payload || '{}');
    } catch {
      setError('Payload must be valid JSON.');
      return;
    }
    requestOperation(point.id, operation, parsed, dryRun)
      .then((r) => { setRun(r); setError(null); onRan(); })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Request failed.'));
  };

  return (
    <div className="border border-rule p-4">
      <div className="flex items-center justify-between">
        <span className="font-serif text-[1.1rem] text-parchment">{point.name}</span>
        {health && <Pill tone={tone(HEALTH_TONE, health.status)}>{iLabel(health.status)}</Pill>}
      </div>
      {health && <p className="mt-1 text-sm text-parchment-muted">{health.detail}</p>}

      {config && (
        <div className="mt-3 font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
          {Object.entries(config.credentials).map(([name, present]) => (
            <span key={name} className="mr-3">
              {name}: <span className={present ? 'text-live' : 'text-signal'}>{present ? 'set' : 'missing'}</span>
            </span>
          ))}
          {config.missing_config.length > 0 && (
            <span className="text-signal">missing config: {config.missing_config.join(', ')}</span>
          )}
        </div>
      )}

      {adapter ? (
        <div className="mt-4 flex flex-col gap-2">
          <Eyebrow>Run an operation</Eyebrow>
          <select className="field-select" value={operation} onChange={(e) => setOperation(e.target.value)}>
            {adapter.operations.map((op) => (
              <option key={op.key} value={op.key}>
                {op.name}{op.requires_approval ? (op.admin_gated ? ' (admin approval)' : ' (approval)') : ''}
              </option>
            ))}
          </select>
          <textarea
            className="field-input font-mono text-[0.7rem]"
            rows={4}
            value={payload}
            onChange={(e) => setPayload(e.target.value)}
            placeholder="payload JSON"
          />
          <label className="flex items-center gap-2 font-mono text-[0.6rem] uppercase tracking-widest text-parchment-dim">
            <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
            dry-run
          </label>
          <button type="button" className="button-accent self-start" onClick={doRun}>Request</button>
        </div>
      ) : (
        <p className="mt-4 font-serif italic text-parchment-muted">
          Descriptive point — no operational adapter bound.
        </p>
      )}

      {error && <p className="mt-2 font-mono text-[0.62rem] text-signal">{error}</p>}
      {run && <div className="mt-4"><RunCard run={run} onChanged={() => { onRan(); fetchPointHealth(point.id).then(setHealth).catch(() => undefined); }} /></div>}
    </div>
  );
}

// --- page ------------------------------------------------------------------

export function IntegrationsHubPage() {
  const [view, setView] = useState<View>('adapters');
  const [adapters, setAdapters] = useState<IntegrationAdapter[]>([]);
  const [points, setPoints] = useState<IntegrationPoint[]>([]);
  const [runs, setRuns] = useState<IntegrationRun[]>([]);
  const [links, setLinks] = useState<IntegrationLink[]>([]);
  const [activePoint, setActivePoint] = useState<IntegrationPoint | null>(null);

  const adapterByKey = useMemo(
    () => new Map(adapters.map((a) => [a.key, a])),
    [adapters],
  );

  useEffect(() => {
    fetchAdapters().then(setAdapters).catch(() => undefined);
  }, []);

  const loadPoints = useCallback(() => {
    fetchPoints().then((p) => setPoints(p.items)).catch(() => undefined);
  }, []);
  const loadRuns = useCallback(() => {
    fetchRuns().then((p) => setRuns(p.items)).catch(() => undefined);
  }, []);
  const loadLinks = useCallback(() => {
    fetchLinks().then((p) => setLinks(p.items)).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (view === 'points') loadPoints();
    if (view === 'runs') loadRuns();
    if (view === 'links') loadLinks();
  }, [view, loadPoints, loadRuns, loadLinks]);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Eyebrow>Studio integrations</Eyebrow>
        <h2 className="mt-2 font-serif text-5xl leading-tight text-parchment">Integration Hub</h2>
        <p className="mt-3 max-w-prose text-parchment-muted">
          Operational but local-first. Read-only operations and dry-runs run immediately;
          mutations await approval; external actions need an administrator and are recorded
          rather than dispatched unless the network is enabled. Secrets live in the
          environment — referenced by name, never stored.
        </p>
      </header>

      <div className="flex items-center gap-2 border-b border-rule pb-3">
        {(['adapters', 'points', 'runs', 'links'] as View[]).map((v) => (
          <button key={v} type="button" onClick={() => setView(v)} className={`nav-link ${view === v ? 'nav-link-active' : ''}`}>
            {iLabel(v)}
          </button>
        ))}
      </div>

      {view === 'adapters' && (
        <div className="grid gap-4 lg:grid-cols-2">
          {adapters.map((a) => (
            <div key={a.key} className="border border-rule p-4">
              <div className="flex items-center justify-between">
                <span className="font-serif text-[1.1rem] text-parchment">{a.name}</span>
                <Pill tone="muted">{iLabel(a.kind)}</Pill>
              </div>
              <p className="mt-1 text-sm text-parchment-muted">{a.description}</p>
              <ul className="mt-3">
                {a.operations.map((op) => (
                  <li key={op.key} className="flex items-center justify-between gap-2 border-t border-rule py-1.5">
                    <span className="text-sm text-parchment-muted">{op.name}</span>
                    <span className="flex items-center gap-1.5">
                      <Pill tone="muted">{op.direction}</Pill>
                      <Pill tone={opTone(op)}>{op.external ? 'external' : op.mutating ? 'mutation' : 'read-only'}</Pill>
                      <Pill tone={tone(RISK_TONE, op.risk)}>{op.risk}</Pill>
                      {op.admin_gated && <Pill tone="signal">admin</Pill>}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {adapters.length === 0 && <p className="font-serif italic text-parchment-muted">No adapters registered.</p>}
        </div>
      )}

      {view === 'points' && (
        <div className="grid gap-6 lg:grid-cols-2">
          <ul>
            {points.map((p) => (
              <li key={p.id} className="border-b border-rule">
                <button type="button" onClick={() => setActivePoint(p)} className="flex w-full items-center justify-between gap-2 px-1 py-2 text-left text-sm transition-colors hover:bg-ink-700/40">
                  <span className="text-parchment-muted">{p.name}</span>
                  <span className="flex items-center gap-2">
                    {p.adapter_key && <span className="font-mono text-[0.56rem] text-parchment-dim">{p.adapter_key}</span>}
                    <Pill tone={p.enabled ? 'live' : 'muted'}>{p.enabled ? 'enabled' : 'off'}</Pill>
                  </span>
                </button>
              </li>
            ))}
            {points.length === 0 && <li className="py-6 font-serif italic text-parchment-muted">No integration points.</li>}
          </ul>
          {activePoint && (
            <PointPanel
              point={activePoint}
              adapter={activePoint.adapter_key ? adapterByKey.get(activePoint.adapter_key) : undefined}
              onRan={loadRuns}
            />
          )}
        </div>
      )}

      {view === 'runs' && (
        <div className="grid gap-4 lg:grid-cols-2">
          {runs.map((r) => <RunCard key={r.id} run={r} onChanged={loadRuns} />)}
          {runs.length === 0 && <p className="font-serif italic text-parchment-muted">No runs yet.</p>}
        </div>
      )}

      {view === 'links' && (
        <ul>
          {links.map((l) => (
            <li key={l.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-rule py-3">
              <span className="flex items-center gap-2">
                <Pill tone="accent">{iLabel(l.external_kind)}</Pill>
                <span className="font-mono text-[0.7rem] text-parchment-muted">{l.external_ref}</span>
                {l.title && <span className="text-parchment-muted">{l.title}</span>}
              </span>
              <span className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">
                → {l.target_type} {l.target_id.slice(0, 8)}
              </span>
            </li>
          ))}
          {links.length === 0 && <li className="py-6 font-serif italic text-parchment-muted">No links yet.</li>}
        </ul>
      )}
    </div>
  );
}
