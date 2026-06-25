import { useEffect, useState, type FormEvent } from 'react';
import { useAuth } from '@/auth/AuthContext';
import { ApiError } from '@/api/client';

/** Members sign-in, overlaid on the home page (no separate landing). */
export function SignInModal({ onClose }: { onClose: () => void }) {
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await signIn(email, password);
      // Success flips AuthProvider to authenticated and App swaps in the studio.
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message || 'Sign-in failed.' : 'Sign-in failed.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/85 px-6 backdrop-blur-sm"
      onClick={onClose}
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
        className="w-full max-w-sm border-2 border-accent bg-ink-800 p-7"
      >
        <div className="flex items-center justify-between">
          <h2 className="font-sans text-2xl font-black uppercase tracking-tight text-parchment">
            Members only
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="font-mono text-parchment-dim transition-colors hover:text-parchment"
          >
            ✕
          </button>
        </div>
        <p className="mt-1 font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
          Studio access
        </p>

        <label className="mt-6 flex flex-col gap-1">
          <span className="font-mono text-[0.6rem] uppercase tracking-widest text-parchment-muted">
            Email
          </span>
          <input
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="field-input w-full"
            autoFocus
            required
          />
        </label>

        <label className="mt-4 flex flex-col gap-1">
          <span className="font-mono text-[0.6rem] uppercase tracking-widest text-parchment-muted">
            Password
          </span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="field-input w-full"
            required
          />
        </label>

        {error && (
          <p className="mt-4 font-mono text-[0.64rem] uppercase tracking-widest text-signal">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="mt-6 w-full bg-accent px-4 py-2 font-mono text-[0.66rem] font-bold uppercase tracking-widest text-ink-900 transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {submitting ? 'Signing in…' : 'Enter the studio'}
        </button>
      </form>
    </div>
  );
}
