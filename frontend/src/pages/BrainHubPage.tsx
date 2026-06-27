import { useEffect, useRef, useState } from 'react';
import { ApiError } from '@/api/client';
import {
  fetchBrainStatus,
  sendBrainChat,
  type BrainCitation,
  type BrainStatus,
} from '@/api/brain';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : 'Request failed';
}

interface ChatProposal {
  tool: string;
  proposal_id?: string | null;
  status?: string | null;
}

interface ChatMsg {
  role: 'user' | 'assistant';
  content: string;
  citations?: BrainCitation[];
  tools?: string[];
  proposals?: ChatProposal[];
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
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchBrainStatus().then(setStatus).catch((e) => setError(errMsg(e)));
  }, []);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const brainUrl = status?.brain_url || null;
  const isDryRun = status?.model?.provider === 'dry_run' || status?.model?.provider === 'unset';

  async function send() {
    const content = input.trim();
    if (!content || sending) return;
    setInput('');
    setError(null);
    setMessages((m) => [...m, { role: 'user', content }]);
    setSending(true);
    try {
      const turn = await sendBrainChat({ content, conversation_id: conversationId });
      setConversationId(turn.conversation_id);
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: turn.content || '(no content)',
          citations: turn.citations,
          tools: turn.tools_used,
          proposals: turn.proposals,
        },
      ]);
    } catch (e) {
      const msg = errMsg(e);
      setError(msg);
      setMessages((m) => [...m, { role: 'assistant', content: `⚠️ ${msg}` }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="p-8">
      <Eyebrow>Brain</Eyebrow>
      <h2 className="mt-2 font-serif text-5xl text-parchment">SUPERVOID Brain</h2>
      <p className="mt-2 max-w-2xl text-parchment-muted">
        Chat with the studio Brain. It answers within your permissions, cites internal evidence,
        and proposes (never auto-executes) governed actions. Use{' '}
        <span className="text-parchment">Ask the Brain</span> from any Work, page, scene, asset or
        task to jump in with that context.
      </p>

      {/* Native in-app chat (no LibreChat / Brain token required). */}
      <div className="mt-6 max-w-3xl border border-rule">
        <div className="flex items-center justify-between border-b border-rule px-4 py-2">
          <Eyebrow>Conversation</Eyebrow>
          <div className="flex items-center gap-2">
            {isDryRun && (
              <Pill tone="signal">dry-run · connect vLLM for real answers</Pill>
            )}
            <span className="font-mono text-[0.55rem] uppercase tracking-widest text-parchment-dim">
              {status?.model?.gateway_model || status?.model?.model || 'supervoid-brain'}
            </span>
          </div>
        </div>

        <div className="flex h-[26rem] flex-col gap-3 overflow-y-auto px-4 py-4">
          {messages.length === 0 && (
            <p className="text-parchment-dim">
              Ask anything about the studio — “What are today’s priorities?”, “Why did we decide the
              antagonist’s identity?”, “What’s blocking production?”
            </p>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={m.role === 'user' ? 'self-end text-right' : 'self-start text-left'}
            >
              <div className="mb-0.5 font-mono text-[0.5rem] uppercase tracking-widest text-parchment-dim">
                {m.role === 'user' ? 'You' : 'Brain'}
              </div>
              <div
                className={
                  'inline-block max-w-[44rem] whitespace-pre-wrap border border-rule px-3 py-2 text-sm ' +
                  (m.role === 'user' ? 'text-parchment' : 'text-parchment-muted')
                }
              >
                {m.content}
                {m.citations && m.citations.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {m.citations.map((c) => (
                      <span
                        key={c.ref}
                        title={c.ref}
                        className="font-mono text-[0.55rem] text-accent"
                      >
                        {c.label}
                      </span>
                    ))}
                  </div>
                )}
                {m.tools && m.tools.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {m.tools.map((t) => (
                      <span
                        key={t}
                        className="border border-rule px-1.5 py-0.5 font-mono text-[0.5rem] uppercase tracking-widest text-parchment-dim"
                      >
                        🔧 {t}
                      </span>
                    ))}
                  </div>
                )}
                {m.proposals && m.proposals.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {m.proposals.map((p, j) => (
                      <span
                        key={p.proposal_id || `${p.tool}-${j}`}
                        title={p.proposal_id || undefined}
                        className="border border-signal/50 px-1.5 py-0.5 font-mono text-[0.5rem] uppercase tracking-widest text-signal"
                      >
                        🔒 {p.tool} · {p.status || 'pending'} — needs approval
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {sending && <p className="self-start font-mono text-[0.6rem] text-parchment-dim">Brain is thinking…</p>}
          <div ref={endRef} />
        </div>

        <div className="flex items-end gap-2 border-t border-rule p-3">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            rows={2}
            placeholder="Message the Brain…  (Enter to send · Shift+Enter for a newline)"
            className="flex-1 resize-none border border-rule bg-transparent px-3 py-2 text-sm text-parchment outline-none placeholder:text-parchment-dim"
          />
          <button
            onClick={() => void send()}
            disabled={sending || !input.trim()}
            className="button-accent disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </div>

      {/* Optional: the LibreChat UI, only when configured. */}
      {brainUrl && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <a href={brainUrl} className="button-accent" target="_blank" rel="noopener noreferrer">
            Open in LibreChat ↗
          </a>
          <span className="font-mono text-[0.55rem] uppercase tracking-widest text-parchment-dim">
            full chat UI · separate sign-in
          </span>
        </div>
      )}

      {error && <p className="mt-4 font-mono text-[0.62rem] text-signal">{error}</p>}

      {status && (
        <div className="mt-8 grid max-w-3xl gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
              <span className="text-parchment-muted">Studio-wide</span>
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
