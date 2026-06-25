import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '@/api/client';
import {
  approveProposal,
  executeProposal,
  fetchAgents,
  fetchFindings,
  fetchProposals,
  fetchRun,
  fetchRuns,
  fetchTools,
  rejectProposal,
  resolveFinding,
  retryRun,
  runAgent,
} from '@/api/agents';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';
import {
  agLabel,
  type AgentDefinition,
  type AgentFinding,
  type AgentProposal,
  type AgentRun,
  type AgentRunDetail,
  type AgentTool,
} from '@/types/agents';

type View = 'registry' | 'runs' | 'findings' | 'proposals';

const SEV_TONE: Record<string, 'muted' | 'accent' | 'signal' | 'live'> = {
  critical: 'signal', high: 'signal', medium: 'accent', low: 'muted', info: 'muted',
};
const STATUS_TONE: Record<string, 'muted' | 'accent' | 'signal' | 'live'> = {
  succeeded: 'live', executed: 'live', approved: 'live', running: 'accent',
  pending: 'accent', failed: 'signal', rejected: 'signal', cancelled: 'muted',
};

function tone(map: Record<string, 'muted' | 'accent' | 'signal' | 'live'>, k: string) {
  return map[k] ?? 'muted';
}

// --- run detail ------------------------------------------------------------

function RunDetail({ run, onChanged }: { run: AgentRunDetail; onChanged: () => void }) {
  return (
    <div className="border border-rule p-4">
      <div className="flex items-center justify-between">
        <Eyebrow>{agLabel(run.agent_key)} · {run.target_type}</Eyebrow>
        <div className="flex items-center gap-2">
          <Pill tone={tone(STATUS_TONE, run.status)}>{agLabel(run.status)}</Pill>
          <button type="button" className="button-quiet" onClick={() => retryRun(run.id).then(onChanged)}>Retry</button>
        </div>
      </div>
      <p className="mt-2 font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
        provider {run.provider} · model {run.model ?? 'stub'} · {run.total_tokens ?? 0} tokens · {run.correlation_id?.slice(0, 8)}
      </p>
      {run.error && <p className="mt-2 font-mono text-[0.62rem] text-signal">{run.error}</p>}

      {run.findings.length > 0 && (
        <div className="mt-3">
          <Eyebrow>Findings</Eyebrow>
          <ul className="mt-1">
            {run.findings.map((f) => (
              <li key={f.id} className="flex items-center gap-2 border-b border-rule py-1.5 text-sm text-parchment-muted">
                <Pill tone={tone(SEV_TONE, f.severity)}>{f.severity}</Pill>
                <span>{f.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {run.proposals.length > 0 && (
        <div className="mt-3">
          <Eyebrow>Proposals</Eyebrow>
          <ul className="mt-1">
            {run.proposals.map((p) => (
              <li key={p.id} className="border-b border-rule py-1.5 text-sm text-parchment-muted">
                <Pill tone="accent">{p.tool_key}</Pill> <Pill tone={tone(SEV_TONE, p.risk_level)}>{p.risk_level}</Pill> {p.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// --- page ------------------------------------------------------------------

export function AgentCentrePage() {
  const [view, setView] = useState<View>('registry');
  const [agents, setAgents] = useState<AgentDefinition[]>([]);
  const [tools, setTools] = useState<AgentTool[]>([]);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [findings, setFindings] = useState<AgentFinding[]>([]);
  const [proposals, setProposals] = useState<AgentProposal[]>([]);
  const [activeRun, setActiveRun] = useState<AgentRunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Run form.
  const [agentKey, setAgentKey] = useState('');
  const [targetType, setTargetType] = useState('');
  const [targetId, setTargetId] = useState('');

  useEffect(() => {
    fetchAgents().then((a) => {
      setAgents(a);
      if (a.length > 0) { setAgentKey(a[0].key); setTargetType(a[0].supported_entity_types[0] ?? ''); }
    });
    fetchTools().then(setTools);
  }, []);

  const loadRuns = useCallback(() => { fetchRuns().then((p) => setRuns(p.items)).catch(() => undefined); }, []);
  const loadFindings = useCallback(() => { fetchFindings({ resolved: false }).then((p) => setFindings(p.items)).catch(() => undefined); }, []);
  const loadProposals = useCallback(() => { fetchProposals('pending').then((p) => setProposals(p.items)).catch(() => undefined); }, []);

  useEffect(() => {
    if (view === 'runs') loadRuns();
    if (view === 'findings') loadFindings();
    if (view === 'proposals') loadProposals();
  }, [view, loadRuns, loadFindings, loadProposals]);

  const doRun = () => {
    if (!agentKey || !targetType || !targetId.trim()) return;
    runAgent(agentKey, targetType, targetId.trim())
      .then((r) => { setActiveRun(r); setError(null); })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Run failed.'));
  };

  const selectedAgent = agents.find((a) => a.key === agentKey);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Eyebrow>Studio agents</Eyebrow>
        <h2 className="mt-2 font-serif text-5xl leading-tight text-parchment">Agent Centre</h2>
        <p className="mt-3 max-w-prose text-parchment-muted">
          Supervised agents: read-only analysis runs immediately; mutations arrive as
          proposals; destructive, publishing, rights and external actions require explicit
          approval. Every run preserves its input snapshot and output.
        </p>
      </header>

      <div className="flex items-center gap-2 border-b border-rule pb-3">
        {(['registry', 'runs', 'findings', 'proposals'] as View[]).map((v) => (
          <button key={v} type="button" onClick={() => setView(v)} className={`nav-link ${view === v ? 'nav-link-active' : ''}`}>
            {agLabel(v)}
          </button>
        ))}
      </div>

      {error && <p className="font-mono text-[0.65rem] uppercase tracking-widest text-signal">{error}</p>}

      {view === 'registry' && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            <Eyebrow>Run an agent</Eyebrow>
            <div className="mt-2 flex flex-col gap-2">
              <select className="field-select" value={agentKey} onChange={(e) => { setAgentKey(e.target.value); const a = agents.find((x) => x.key === e.target.value); setTargetType(a?.supported_entity_types[0] ?? ''); }}>
                {agents.map((a) => (<option key={a.key} value={a.key}>{a.name}</option>))}
              </select>
              {selectedAgent && (
                <p className="font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
                  {agLabel(selectedAgent.mutability)} · tools: {selectedAgent.allowed_tools.join(', ')}
                </p>
              )}
              <div className="flex gap-2">
                <select className="field-select" value={targetType} onChange={(e) => setTargetType(e.target.value)}>
                  {(selectedAgent?.supported_entity_types ?? []).map((t) => (<option key={t} value={t}>{t}</option>))}
                </select>
                <input className="field-input flex-1" placeholder="target id" value={targetId} onChange={(e) => setTargetId(e.target.value)} />
                <button type="button" className="button-accent" onClick={doRun} disabled={!targetId.trim()}>Run</button>
              </div>
            </div>
            {activeRun && <div className="mt-4"><RunDetail run={activeRun} onChanged={() => setActiveRun(null)} /></div>}

            <div className="mt-6">
              <Eyebrow>Agents</Eyebrow>
              <ul className="mt-2">
                {agents.map((a) => (
                  <li key={a.key} className="border-b border-rule py-2">
                    <div className="flex items-center justify-between">
                      <span className="font-serif text-[1rem] text-parchment">{a.name}</span>
                      <Pill tone={a.mutability === 'read_only' ? 'muted' : 'accent'}>{agLabel(a.mutability)}</Pill>
                    </div>
                    <p className="text-sm text-parchment-muted">{a.description}</p>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div>
            <Eyebrow>Tool registry</Eyebrow>
            <ul className="mt-2">
              {tools.map((t) => (
                <li key={t.key} className="flex items-center justify-between gap-2 border-b border-rule py-2">
                  <span className="text-sm text-parchment-muted">{t.name}</span>
                  <span className="flex items-center gap-1.5">
                    <Pill tone={t.kind === 'read_only' ? 'muted' : t.kind === 'external' ? 'signal' : 'accent'}>{agLabel(t.kind)}</Pill>
                    <Pill tone={tone(SEV_TONE, t.risk_level)}>{t.risk_level}</Pill>
                    {t.always_requires_approval && <Pill tone="signal">gated</Pill>}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {view === 'runs' && (
        <div className="grid gap-6 lg:grid-cols-2">
          <ul>
            {runs.map((r) => (
              <li key={r.id} className="border-b border-rule">
                <button type="button" onClick={() => fetchRun(r.id).then(setActiveRun)} className="flex w-full items-center justify-between gap-2 px-1 py-2 text-left text-sm transition-colors hover:bg-ink-700/40">
                  <span className="text-parchment-muted">{agLabel(r.agent_key)} · {r.target_type}</span>
                  <span className="flex items-center gap-2">
                    <span className="font-mono text-[0.56rem] text-parchment-dim">{r.finding_count}f/{r.proposal_count}p</span>
                    <Pill tone={tone(STATUS_TONE, r.status)}>{agLabel(r.status)}</Pill>
                  </span>
                </button>
              </li>
            ))}
            {runs.length === 0 && <li className="py-6 font-serif italic text-parchment-muted">No runs yet.</li>}
          </ul>
          {activeRun && <RunDetail run={activeRun} onChanged={loadRuns} />}
        </div>
      )}

      {view === 'findings' && (
        <ul>
          {findings.map((f) => (
            <li key={f.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-rule py-3">
              <span className="flex items-center gap-2">
                <Pill tone={tone(SEV_TONE, f.severity)}>{f.severity}</Pill>
                <span className="text-parchment-muted">{f.message}</span>
                {f.category && <span className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">{f.category}</span>}
              </span>
              <button type="button" className="button-quiet" onClick={() => resolveFinding(f.id).then(loadFindings)}>Resolve</button>
            </li>
          ))}
          {findings.length === 0 && <li className="py-6 font-serif italic text-parchment-muted">Inbox clear.</li>}
        </ul>
      )}

      {view === 'proposals' && (
        <ul>
          {proposals.map((p) => (
            <li key={p.id} className="border-b border-rule py-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="flex items-center gap-2">
                  <Pill tone="accent">{p.tool_key}</Pill>
                  <Pill tone={tone(SEV_TONE, p.risk_level)}>{p.risk_level}</Pill>
                  <span className="text-parchment-muted">{p.reason}</span>
                </span>
                <span className="flex items-center gap-2">
                  <button type="button" className="button-accent" onClick={() => approveProposal(p.id).then(loadProposals).catch((e) => setError(e instanceof ApiError ? e.message : 'Approve failed.'))}>Approve</button>
                  <button type="button" className="button-quiet" onClick={() => rejectProposal(p.id).then(loadProposals)}>Reject</button>
                  <button type="button" className="button-quiet" onClick={() => executeProposal(p.id).then(loadProposals).catch((e) => setError(e instanceof ApiError ? e.message : 'Execute (approve first).'))}>Execute</button>
                </span>
              </div>
            </li>
          ))}
          {proposals.length === 0 && <li className="py-6 font-serif italic text-parchment-muted">No pending proposals.</li>}
        </ul>
      )}
    </div>
  );
}
