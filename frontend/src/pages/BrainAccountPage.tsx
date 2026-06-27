import { useEffect, useState } from 'react';
import { ApiError } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { fetchMyIdentity, type MyIdentity } from '@/api/identity';
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

export function BrainAccountPage() {
  const { user } = useAuth();
  const [identity, setIdentity] = useState<MyIdentity | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMyIdentity().then(setIdentity).catch((e) => setError(errMsg(e)));
  }, []);

  const endpoint = `${window.location.origin}/brain/v1`;

  return (
    <div className="p-8">
      <Eyebrow>Brain · Account</Eyebrow>
      <h2 className="mt-2 font-serif text-5xl text-parchment">Your Brain Account</h2>
      <p className="mt-2 max-w-2xl text-parchment-muted">
        Your SUPERVOID account ({user?.email}) and its link to the Brain (LibreChat).
        Access always runs as <span className="text-parchment">you</span> — the Brain
        only ever sees what your SUPERVOID permissions allow.
      </p>

      {error && <p className="mt-4 font-mono text-[0.62rem] text-signal">{error}</p>}

      <section className="mt-6 border border-rule p-4">
        <Eyebrow>LibreChat identity link</Eyebrow>
        {identity === null ? (
          <p className="mt-2 text-parchment-muted">Loading…</p>
        ) : identity.linked ? (
          <div className="mt-3 flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <Pill tone={STATUS_TONE[identity.status ?? 'pending'] ?? 'muted'}>
                {identity.status}
              </Pill>
              <span className="font-mono text-[0.7rem] text-parchment">{identity.librechat_email}</span>
            </div>
            {identity.status === 'active' ? (
              <p className="text-[0.8rem] text-parchment-muted">
                Your account is linked and verified — you can use the Brain.
              </p>
            ) : identity.status === 'pending' ? (
              <p className="text-[0.8rem] text-parchment-muted">
                Linked but awaiting verification by an administrator.
              </p>
            ) : (
              <p className="text-[0.8rem] text-signal">
                This link is {identity.status}. Contact an administrator to restore Brain access.
              </p>
            )}
          </div>
        ) : (
          <p className="mt-3 text-parchment-muted">
            Your account isn’t linked to a LibreChat identity yet. Ask an administrator to link
            you — self-registration in the Brain is disabled by design.
          </p>
        )}
      </section>

      <section className="mt-6 border border-rule p-4">
        <Eyebrow>Brain Gateway endpoint</Eyebrow>
        <code className="mt-2 block break-all font-mono text-[0.72rem] text-parchment">{endpoint}</code>
        <p className="mt-2 text-[0.8rem] text-parchment-muted">
          Create and manage your personal access tokens on the{' '}
          <span className="text-parchment">Brain Tokens</span> page. A token's secret is shown
          once; you can rotate or revoke it at any time.
        </p>
      </section>
    </div>
  );
}
