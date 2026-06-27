import { useEffect, useState } from 'react';
import { ApiError } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import {
  createIdentityLink,
  disableIdentityLink,
  fetchAdminUsersSafe,
  listIdentityLinks,
  listSecurityEvents,
  verifyIdentityLink,
  type AdminUser,
  type IdentityLink,
  type SecurityEvent,
} from '@/api/identity';
import { Eyebrow } from '@/components/Eyebrow';
import { Pill } from '@/components/Pill';

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : 'Request failed';
}

const STATUS_TONE: Record<string, 'accent' | 'live' | 'muted' | 'signal'> = {
  active: 'live',
  pending: 'accent',
  disabled: 'signal',
  revoked: 'signal',
};

const SEV_TONE: Record<string, 'accent' | 'live' | 'muted' | 'signal'> = {
  info: 'muted',
  warning: 'accent',
  critical: 'signal',
};

export function IdentityAccessPage() {
  const { user } = useAuth();
  const [links, setLinks] = useState<IdentityLink[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [userId, setUserId] = useState('');
  const [lcEmail, setLcEmail] = useState('');
  const [lcUserId, setLcUserId] = useState('');
  const [verifyNow, setVerifyNow] = useState(true);

  const isAdmin = user?.role === 'admin';

  const load = () => {
    if (!isAdmin) return;
    listIdentityLinks().then(setLinks).catch((e) => setError(errMsg(e)));
    fetchAdminUsersSafe().then(setUsers).catch(() => undefined);
    listSecurityEvents().then(setEvents).catch(() => undefined);
  };

  useEffect(load, [isAdmin]);

  if (!isAdmin) {
    return (
      <div className="p-8">
        <Eyebrow>Identity</Eyebrow>
        <h2 className="mt-2 font-serif text-5xl text-parchment">Identity &amp; Access</h2>
        <p className="mt-3 text-parchment-muted">Identity administration is restricted to administrators.</p>
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

  const submitLink = () => {
    if (!userId || !lcEmail.trim()) return;
    run(() =>
      createIdentityLink({
        supervoid_user_id: userId,
        librechat_email: lcEmail.trim(),
        librechat_user_id: lcUserId.trim() || null,
        verify: verifyNow,
      }).then(() => {
        setLcEmail('');
        setLcUserId('');
      }),
    );
  };

  return (
    <div className="p-8">
      <Eyebrow>Identity</Eyebrow>
      <h2 className="mt-2 font-serif text-5xl text-parchment">Identity &amp; Access</h2>
      <p className="mt-2 max-w-2xl text-parchment-muted">
        Link a SUPERVOID member to their LibreChat identity. Only an{' '}
        <span className="text-parchment">active</span> link may authenticate the Brain via MCP —
        unlinked or disabled identities are rejected. LibreChat self-registration is disabled.
      </p>

      {error && <p className="mt-4 font-mono text-[0.62rem] text-signal">{error}</p>}

      {/* Create link */}
      <section className="mt-6 border border-rule p-4">
        <Eyebrow>Link a member</Eyebrow>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <select className="field-select" value={userId} onChange={(e) => setUserId(e.target.value)} aria-label="SUPERVOID user">
            <option value="">Select SUPERVOID user…</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name} · {u.email}{u.is_active ? '' : ' (disabled)'}
              </option>
            ))}
          </select>
          <input className="field-input" placeholder="LibreChat email" value={lcEmail} onChange={(e) => setLcEmail(e.target.value)} />
          <input className="field-input" placeholder="LibreChat user id (optional)" value={lcUserId} onChange={(e) => setLcUserId(e.target.value)} />
          <label className="flex items-center gap-2 text-[0.7rem] text-parchment-muted">
            <input type="checkbox" checked={verifyNow} onChange={(e) => setVerifyNow(e.target.checked)} />
            Verify immediately (set active)
          </label>
        </div>
        <button type="button" className="button-accent mt-3" disabled={busy || !userId || !lcEmail.trim()} onClick={submitLink}>
          Link member
        </button>
      </section>

      {/* Links */}
      <section className="mt-8">
        <div className="flex items-baseline justify-between border-b border-rule pb-3">
          <span className="font-mono text-[0.65rem] uppercase tracking-widest text-parchment-dim">Identity links</span>
          <span className="font-mono text-[0.65rem] text-parchment-muted">{links.length}</span>
        </div>
        {links.length === 0 && <p className="py-6 font-serif italic text-parchment-muted">No identity links yet.</p>}
        <ul>
          {links.map((l) => (
            <li key={l.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-rule py-3">
              <div>
                <span className="text-parchment">{l.user_email || l.supervoid_user_id}</span>
                <span className="ml-2 font-mono text-[0.6rem] text-parchment-dim">→ {l.librechat_email}</span>
              </div>
              <div className="flex items-center gap-2">
                <Pill tone={STATUS_TONE[l.status] ?? 'muted'}>{l.status}</Pill>
                {l.status !== 'active' && (
                  <button type="button" className="button-ghost" disabled={busy} onClick={() => run(() => verifyIdentityLink(l.id))}>
                    Verify
                  </button>
                )}
                {l.status === 'active' && (
                  <button type="button" className="button-ghost" disabled={busy} onClick={() => run(() => disableIdentityLink(l.id))}>
                    Disable
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </section>

      {/* Security events */}
      <section className="mt-8">
        <div className="flex items-baseline justify-between border-b border-rule pb-3">
          <span className="font-mono text-[0.65rem] uppercase tracking-widest text-parchment-dim">Recent security events</span>
          <span className="font-mono text-[0.65rem] text-parchment-muted">{events.length}</span>
        </div>
        {events.length === 0 && <p className="py-6 font-serif italic text-parchment-muted">No security events recorded.</p>}
        <ul>
          {events.map((ev) => (
            <li key={ev.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-rule py-2">
              <div className="flex items-center gap-2">
                <Pill tone={SEV_TONE[ev.severity] ?? 'muted'}>{ev.severity}</Pill>
                <span className="font-mono text-[0.62rem] text-parchment">{ev.event_type}</span>
                <span className="font-mono text-[0.58rem] text-parchment-dim">{ev.source}</span>
              </div>
              <div className="font-mono text-[0.58rem] text-parchment-muted">
                {ev.email || ev.supervoid_user_id || '—'}{ev.reason ? ` · ${ev.reason}` : ''}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
