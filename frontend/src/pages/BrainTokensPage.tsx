import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '@/api/client';
import {
  createBrainToken,
  listBrainTokens,
  revokeBrainToken,
  rotateBrainToken,
  type BrainTokenMeta,
  type BrainTokenSecret,
} from '@/api/brainTokens';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : 'Request failed';
}

function fmt(ts: string | null): string {
  return ts ? new Date(ts).toLocaleString() : '—';
}

function tokenStatus(t: BrainTokenMeta): { label: string; tone: 'live' | 'signal' | 'muted' } {
  if (t.revoked_at) return { label: 'revoked', tone: 'signal' };
  if (t.expires_at && new Date(t.expires_at).getTime() < Date.now())
    return { label: 'expired', tone: 'signal' };
  return { label: 'active', tone: 'live' };
}

/** The plaintext secret is shown exactly once. This banner is the only place a
 * user can copy it; after dismissal it is unrecoverable. */
function SecretBanner({ secret, onDismiss }: { secret: BrainTokenSecret; onDismiss: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(secret.secret);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard may be unavailable; the field is selectable as a fallback */
    }
  };
  return (
    <div className="mt-6 border border-accent/50 bg-accent/5 p-4">
      <Eyebrow>New token · {secret.token.name}</Eyebrow>
      <p className="mt-2 text-sm text-parchment-muted">
        Copy this secret now — it is shown <strong className="text-parchment">only once</strong> and
        cannot be retrieved later. Paste it into LibreChat as the API key.
      </p>
      <div className="mt-3 flex items-center gap-2">
        <code className="flex-1 select-all overflow-x-auto whitespace-nowrap border border-rule bg-ink-900/60 px-3 py-2 font-mono text-[0.72rem] text-parchment">
          {secret.secret}
        </code>
        <button type="button" className="button-accent" onClick={copy}>
          {copied ? 'Copied' : 'Copy'}
        </button>
        <button type="button" className="button-outline" onClick={onDismiss}>
          Done
        </button>
      </div>
    </div>
  );
}

export function BrainTokensPage() {
  const [tokens, setTokens] = useState<BrainTokenMeta[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reveal, setReveal] = useState<BrainTokenSecret | null>(null);

  // Create form
  const [name, setName] = useState('');
  const [expiresDays, setExpiresDays] = useState('');

  const load = useCallback(() => {
    listBrainTokens()
      .then(setTokens)
      .catch((e) => setError(errMsg(e)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const create = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const days = expiresDays.trim() ? Number(expiresDays) : null;
      const secret = await createBrainToken({
        name: name.trim(),
        expires_in_days: days && days > 0 ? days : null,
      });
      setReveal(secret);
      setName('');
      setExpiresDays('');
      load();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  const rotate = async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      const secret = await rotateBrainToken(id);
      setReveal(secret);
      load();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (id: string, name: string) => {
    if (!window.confirm(`Revoke "${name}"? Any client using it will stop working immediately.`))
      return;
    setBusy(true);
    setError(null);
    try {
      await revokeBrainToken(id);
      load();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  const gatewayBase = `${window.location.origin}/brain/v1`;

  return (
    <div className="p-8">
      <Eyebrow>Brain Gateway</Eyebrow>
      <h2 className="mt-2 font-serif text-5xl text-parchment">Access Tokens</h2>
      <p className="mt-2 max-w-2xl text-parchment-muted">
        Dedicated bearer tokens for the OpenAI-compatible Brain Gateway. LibreChat (and any OpenAI
        client) authenticates with one of these — never your browser session or the upstream model
        key. Only a one-way hash is stored; the secret is shown once at creation.
      </p>

      <div className="mt-4 border border-rule p-3">
        <Eyebrow>Gateway endpoint</Eyebrow>
        <code className="mt-1 block select-all font-mono text-[0.7rem] text-parchment">
          {gatewayBase}
        </code>
      </div>

      {error && <p className="mt-4 font-mono text-[0.62rem] text-signal">{error}</p>}

      {reveal && <SecretBanner secret={reveal} onDismiss={() => setReveal(null)} />}

      {/* Create */}
      <div className="mt-8 border border-rule p-4">
        <Eyebrow>Issue a new token</Eyebrow>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
              Name
            </span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="LibreChat · my laptop"
              className="w-64 border border-rule bg-ink-900/40 px-3 py-2 text-sm text-parchment focus:border-accent focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
              Expires in days (optional)
            </span>
            <input
              value={expiresDays}
              onChange={(e) => setExpiresDays(e.target.value.replace(/[^0-9]/g, ''))}
              placeholder="never"
              inputMode="numeric"
              className="w-40 border border-rule bg-ink-900/40 px-3 py-2 text-sm text-parchment focus:border-accent focus:outline-none"
            />
          </label>
          <button
            type="button"
            disabled={busy || !name.trim()}
            className="button-accent"
            onClick={create}
          >
            Create token
          </button>
        </div>
      </div>

      {/* List */}
      <div className="mt-8">
        <Eyebrow>Your tokens</Eyebrow>
        {tokens.length === 0 ? (
          <p className="mt-3 text-parchment-muted">No tokens yet. Create one to connect LibreChat.</p>
        ) : (
          <table className="mt-3 w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-rule text-left font-mono text-[0.56rem] uppercase tracking-widest text-parchment-dim">
                <th className="py-2 pr-4">Name</th>
                <th className="py-2 pr-4">Prefix</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4">Last used</th>
                <th className="py-2 pr-4">Expires</th>
                <th className="py-2 pr-4">Created</th>
                <th className="py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {tokens.map((t) => {
                const st = tokenStatus(t);
                const dead = !!t.revoked_at;
                return (
                  <tr key={t.id} className="border-b border-rule/60">
                    <td className="py-2 pr-4 text-parchment">{t.name}</td>
                    <td className="py-2 pr-4 font-mono text-[0.68rem] text-parchment-muted">
                      {t.token_prefix}…
                    </td>
                    <td className="py-2 pr-4">
                      <Pill tone={st.tone}>{st.label}</Pill>
                    </td>
                    <td className="py-2 pr-4 text-parchment-muted">{fmt(t.last_used_at)}</td>
                    <td className="py-2 pr-4 text-parchment-muted">{fmt(t.expires_at)}</td>
                    <td className="py-2 pr-4 text-parchment-muted">{fmt(t.created_at)}</td>
                    <td className="py-2 text-right">
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          disabled={busy || dead}
                          className="button-outline disabled:opacity-40"
                          onClick={() => rotate(t.id)}
                        >
                          Rotate
                        </button>
                        <button
                          type="button"
                          disabled={busy || dead}
                          className="font-mono text-[0.6rem] uppercase tracking-widest text-signal/90 transition-colors hover:text-signal disabled:opacity-40"
                          onClick={() => revoke(t.id, t.name)}
                        >
                          Revoke
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
