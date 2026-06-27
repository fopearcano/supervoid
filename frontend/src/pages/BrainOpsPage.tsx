import { useEffect, useState } from 'react';
import { ApiError } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import {
  fetchOpsStatus,
  markProjectCold,
  rebuildProject,
  replayEvents,
  setDrain,
  setMcp,
  setModelRequests,
  type OpsStatus,
} from '@/api/ops';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : 'Request failed';
}

const STATE_TONE: Record<string, 'accent' | 'live' | 'muted' | 'signal'> = {
  healthy: 'live',
  degraded: 'signal',
  unavailable: 'signal',
  stale: 'accent',
  maintenance: 'accent',
};

function Card({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border border-rule p-4">
      <Eyebrow>{label}</Eyebrow>
      <div className="mt-2 space-y-1 font-mono text-[0.72rem] text-parchment">{children}</div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-parchment-dim">{k}</span>
      <span className="text-parchment">{v}</span>
    </div>
  );
}

export function BrainOpsPage() {
  const { user } = useAuth();
  const [s, setS] = useState<OpsStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [workId, setWorkId] = useState('');

  const isAdmin = user?.role === 'admin';

  const load = () => {
    if (!isAdmin) return;
    fetchOpsStatus().then(setS).catch((e) => setError(errMsg(e)));
  };

  useEffect(load, [isAdmin]);

  if (!isAdmin) {
    return (
      <div className="p-8">
        <Eyebrow>Brain</Eyebrow>
        <h2 className="mt-2 font-serif text-5xl text-parchment">Brain Operations</h2>
        <p className="mt-3 text-parchment-muted">Brain Operations is restricted to administrators.</p>
      </div>
    );
  }

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      load();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  const health = s?.health;
  const gw = s?.gateway ?? {};
  const comp = s?.compiler ?? {};
  const vllm = s?.vllm ?? {};
  const usage = s?.usage ?? {};
  const sessions = s?.sessions ?? {};

  return (
    <div className="p-8">
      <Eyebrow>Brain · Operations</Eyebrow>
      <h2 className="mt-2 font-serif text-5xl text-parchment">Brain Operations</h2>
      <p className="mt-2 max-w-2xl text-parchment-muted">
        Internal observability + operational controls. Admin-only; GPU and topology
        are never exposed on public endpoints.
      </p>

      {error && <p className="mt-4 font-mono text-[0.62rem] text-signal">{error}</p>}

      {/* health banner */}
      {health && (
        <div className="mt-6 flex flex-wrap items-center gap-3 border border-rule p-3">
          <span className="font-mono text-[0.6rem] uppercase tracking-widest text-parchment-dim">overall</span>
          <Pill tone={STATE_TONE[health.overall] ?? 'muted'}>{health.overall}</Pill>
          {Object.entries(health.components || {}).map(([k, v]) => (
            <span key={k} className="flex items-center gap-1 font-mono text-[0.6rem] text-parchment-muted">
              {k}: <Pill tone={STATE_TONE[v as string] ?? 'muted'}>{v as string}</Pill>
            </span>
          ))}
          <button type="button" className="button-ghost ml-auto" onClick={load}>Refresh</button>
        </div>
      )}

      {s && (
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Card label="vLLM / model">
            <Row k="provider" v={vllm.provider} />
            <Row k="reachable" v={String(vllm.reachable)} />
            <Row k="loaded model" v={vllm.loaded_model || '—'} />
            <Row k="context limit" v={vllm.context_limit} />
            <Row k="GPU" v={vllm.gpu_utilisation ?? 'n/a'} />
            <Row k="latency ms" v={vllm.latency_ms ?? '—'} />
          </Card>
          <Card label="Gateway">
            <Row k="active requests" v={gw.active_requests} />
            <Row k="queue depth" v={gw.queue_depth} />
            <Row k="capacity" v={gw.capacity} />
            <Row k="model requests" v={gw.model_requests_disabled ? 'disabled' : 'enabled'} />
            <Row k="draining" v={String(gw.draining)} />
            <Row k="mcp" v={gw.mcp_disabled ? 'disabled' : 'enabled'} />
          </Card>
          <Card label="Compiler / outbox">
            <Row k="head sequence" v={comp.head_sequence} />
            <Row k="compiler lag" v={comp.compiler_lag} />
            <Row k="unprocessed events" v={comp.unprocessed_events} />
            <Row k="failed events" v={comp.failed_events} />
            <Row k="stale projects" v={comp.stale_projects} />
            <Row k="studio version" v={comp.studio_version ?? '—'} />
          </Card>
          <Card label="Sessions">
            <Row k="active conversations" v={s.active_conversations} />
            <Row k="sessions" v={sessions.total} />
            <Row k="prefix hashes" v={sessions.distinct_prefix_hashes} />
            <Row k="warmth" v={JSON.stringify(sessions.by_warmth || {})} />
          </Card>
          <Card label="Usage / latency">
            <Row k="prompt tokens" v={usage.prompt_tokens_total} />
            <Row k="completion tokens" v={usage.completion_tokens_total} />
            <Row k="TTFT avg ms" v={usage.ttft_ms_avg ?? '—'} />
            <Row k="latency avg ms" v={usage.latency_ms_avg ?? '—'} />
          </Card>
          <Card label="Agents / MCP / proposals">
            <Row k="agent failures" v={s.agent_failures} />
            <Row k="mcp failures" v={s.mcp_failures} />
            <Row k="pending proposals" v={s.pending_proposals} />
            <Row k="librechat" v={String(s.librechat?.reachable ?? 'unknown')} />
          </Card>
        </div>
      )}

      {/* controls */}
      <section className="mt-8 border border-rule p-4">
        <Eyebrow>Operational controls</Eyebrow>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" className="button-ghost" disabled={busy}
                  onClick={() => run(() => setModelRequests(!!gw.model_requests_disabled))}>
            {gw.model_requests_disabled ? 'Enable model requests' : 'Disable model requests'}
          </button>
          <button type="button" className="button-ghost" disabled={busy}
                  onClick={() => run(() => setDrain(!gw.draining))}>
            {gw.draining ? 'Resume' : 'Drain'}
          </button>
          <button type="button" className="button-ghost" disabled={busy}
                  onClick={() => run(() => setMcp(!!gw.mcp_disabled))}>
            {gw.mcp_disabled ? 'Enable MCP' : 'Disable MCP'}
          </button>
          <button type="button" className="button-ghost" disabled={busy}
                  onClick={() => run(() => replayEvents())}>
            Replay failed events
          </button>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <input className="field-input" placeholder="work id" value={workId}
                 onChange={(e) => setWorkId(e.target.value)} />
          <button type="button" className="button-ghost" disabled={busy || !workId.trim()}
                  onClick={() => run(() => rebuildProject(workId.trim()))}>
            Rebuild project state
          </button>
          <button type="button" className="button-ghost" disabled={busy || !workId.trim()}
                  onClick={() => run(() => markProjectCold(workId.trim()))}>
            Mark project cold
          </button>
        </div>
      </section>
    </div>
  );
}
