import { useState } from 'react';
import { ApiError } from '@/api/client';
import { requestBrainHandoff } from '@/api/brain';

interface AskBrainButtonProps {
  entityType: string;
  entityId: string;
  /** Optional assistant profile to request (defaults to the Studio Director). */
  profile?: string;
  label?: string;
  className?: string;
}

/**
 * Context-aware "Ask the Brain": mints a signed, short-lived hand-off on the
 * server (which binds a BrainConversation to this entity's project), then
 * redirects to the hand-off landing endpoint → LibreChat. No project content is
 * ever placed in the URL — only the opaque token the server returns.
 */
export function AskBrainButton({
  entityType,
  entityId,
  profile,
  label = 'Ask the Brain',
  className = '',
}: AskBrainButtonProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      const handoff = await requestBrainHandoff(entityType, entityId, profile);
      // Full-page navigation to the (reverse-proxied) landing endpoint.
      window.location.assign(handoff.handoff_url);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not open the Brain');
      setBusy(false);
    }
  };

  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <button
        type="button"
        onClick={go}
        disabled={busy || !entityId}
        className="button-outline disabled:opacity-50"
        title="Open this in the SUPERVOID Brain"
      >
        {busy ? 'Opening…' : `🧠 ${label}`}
      </button>
      {error && (
        <span className="font-mono text-[0.58rem] text-signal">{error}</span>
      )}
    </span>
  );
}
