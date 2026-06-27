import { useEffect, useState } from 'react';
import { ApiError } from '@/api/client';
import { fetchBrainStatus, type BrainStatus } from '@/api/brain';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : 'Request failed';
}

function StatCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border border-rule p-4">
      <Eyebrow>{label}</Eyebrow>
      <div className="mt-2 text-parchment">{children}</div>
    </div>
  );
}

export function BrainHubPage() {
  const [status, setStatus] = useState<BrainStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchBrainStatus().then(setStatus).catch((e) => setError(errMsg(e)));
  }, []);

  const brainUrl = status?.brain_url || '/brain/';

  return (
    <div className="p-8">
      <Eyebrow>Brain</Eyebrow>
      <h2 className="mt-2 font-serif text-5xl text-parchment">SUPERVOID Brain</h2>
      <p className="mt-2 max-w-2xl text-parchment-muted">
        The conversational interface to the studio Brain. Open it to chat, or use{' '}
        <span className="text-parchment">Ask the Brain</span> from any Work, Story World,
        page, panel, scene, shot, asset, task or rights record to jump in with that context.
      </p>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        {brainUrl ? (
          <>
            <a href={brainUrl} className="button-accent" target="_blank" rel="noopener noreferrer">
              🧠 Open the Brain
            </a>
            <span className="font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
              opens LibreChat · separate sign-in
            </span>
          </>
        ) : (
          <span className="max-w-2xl font-mono text-[0.62rem] leading-relaxed text-parchment-muted">
            LibreChat is not configured. Set <span className="text-parchment">LIBRECHAT_PUBLIC_URL</span> and
            run <span className="text-parchment">deploy/brain</span> to use the chat UI — or talk to the
            OpenAI-compatible gateway directly at <span className="text-parchment">/brain/v1</span> with a
            Brain Token. See <span className="text-parchment">docs/LIBRECHAT_INTEGRATION.md</span>. The status
            below works regardless.
          </span>
        )}
      </div>

      {error && <p className="mt-4 font-mono text-[0.62rem] text-signal">{error}</p>}

      {status && (
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <StatCard label="Active project">
            {status.active_project ? (
              <span>
                {status.active_project.label || status.active_project.work_id ||
                  status.active_project.story_world_id}
                <span className="ml-2 font-mono text-[0.55rem] uppercase tracking-widest text-parchment-dim">
                  {status.active_project.entity_type}
                </span>
              </span>
            ) : (
              <span className="text-parchment-muted">None selected</span>
            )}
          </StatCard>

          <StatCard label="State version">
            <span className="font-mono">
              {status.state_version != null ? `v${status.state_version}` : '—'}
            </span>
          </StatCard>

          <StatCard label="Model">
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone="accent">{status.model.provider || 'unset'}</Pill>
              <span className="font-mono text-[0.66rem] text-parchment-muted">
                {status.model.gateway_model || status.model.model}
              </span>
            </div>
          </StatCard>

          <StatCard label="Compiler">
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone={status.compiler.studio_stale ? 'signal' : 'live'}>
                {status.compiler.studio_stale ? 'stale' : 'fresh'}
              </Pill>
              <span className="font-mono text-[0.6rem] text-parchment-muted">
                head {status.compiler.head_sequence ?? '—'} · stale projects{' '}
                {status.compiler.stale_projects ?? 0}
              </span>
            </div>
          </StatCard>

          <StatCard label="Pending proposals">
            <span className="font-mono text-2xl">{status.pending_proposals}</span>
            <span className="ml-2 text-parchment-muted">awaiting review</span>
          </StatCard>
        </div>
      )}
    </div>
  );
}
