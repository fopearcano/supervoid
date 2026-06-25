import { useEffect, useState, type FormEvent } from 'react';
import { useAuth } from '@/auth/AuthContext';
import { ApiError } from '@/api/client';
import { ThemeToggle } from '@/components/ThemeToggle';

interface ShowcaseWork {
  id: string;
  slug: string;
  title: string;
  author_credit?: string | null;
  public_synopsis?: string | null;
  tags?: string[];
}

/** A minimal public showcase pulled from the read-only public reader API
 * (`/public/works`). Best-effort: failures and empties degrade quietly. */
function useShowcase(): ShowcaseWork[] | null {
  const [works, setWorks] = useState<ShowcaseWork[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch('/public/works', { headers: { Accept: 'application/json' } })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => {
        if (!cancelled) setWorks(Array.isArray(data) ? data.slice(0, 4) : []);
      })
      .catch(() => {
        if (!cancelled) setWorks([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return works;
}

export function LandingPage({ onBack }: { onBack?: () => void }) {
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const works = useShowcase();

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await signIn(email, password);
      // On success the AuthProvider flips to "authenticated" and App swaps in
      // the studio shell — nothing more to do here.
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message || 'Sign-in failed.' : 'Sign-in failed.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative min-h-screen bg-ink-800">
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          className="absolute left-6 top-6 z-10 font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim transition-colors hover:text-parchment"
        >
          ← Home
        </button>
      )}
      <div className="absolute right-6 top-6 z-10">
        <ThemeToggle />
      </div>

      <div className="mx-auto flex min-h-screen max-w-editorial flex-col justify-center gap-14 px-8 py-20 lg:flex-row lg:items-center lg:gap-20">
        {/* Identity + showcase */}
        <section className="flex-1">
          <p className="font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim">
            In-house studio system
          </p>
          <h1 className="mt-3 font-serif text-6xl leading-none tracking-tight text-parchment">
            SUPERVOID
            <span className="ml-3 align-middle font-mono text-sm uppercase tracking-widest text-parchment-muted">
              Publishing
            </span>
          </h1>
          <p className="mt-6 max-w-xl text-[1.05rem] leading-relaxed text-parchment-muted">
            The private operating system for an independent transmedia studio —
            story worlds, manuscripts, graphic novels, screen adaptations, the
            asset library, rights and the public reader, in one place.
          </p>

          <div className="mt-12">
            <div className="flex items-baseline justify-between border-b border-rule pb-2">
              <span className="font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim">
                From the public reader
              </span>
              <a
                href="/reader"
                className="font-mono text-[0.62rem] uppercase tracking-widest text-accent transition-colors hover:text-parchment"
              >
                Open the reader →
              </a>
            </div>

            {works === null ? (
              <p className="mt-4 font-mono text-[0.66rem] uppercase tracking-widest text-parchment-dim">
                Loading…
              </p>
            ) : works.length === 0 ? (
              <p className="mt-4 font-serif italic text-parchment-muted">
                No public works published yet.
              </p>
            ) : (
              <ul className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
                {works.map((work) => (
                  <li key={work.id}>
                    <a href="/reader" className="group block">
                      <div className="text-base text-parchment transition-colors group-hover:text-accent">
                        {work.title}
                      </div>
                      {work.author_credit && (
                        <div className="font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
                          {work.author_credit}
                        </div>
                      )}
                      {work.public_synopsis && (
                        <p className="mt-1 line-clamp-2 text-sm text-parchment-muted">
                          {work.public_synopsis}
                        </p>
                      )}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        {/* Sign-in */}
        <section className="w-full lg:w-[22rem] lg:shrink-0">
          <form
            onSubmit={onSubmit}
            className="border border-rule bg-ink-900/40 p-7"
          >
            <h2 className="font-serif text-2xl text-parchment">Sign in</h2>
            <p className="mt-1 font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
              Studio access only
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
              className="mt-6 w-full border border-accent px-4 py-2 font-mono text-[0.66rem] uppercase tracking-widest text-accent transition-colors hover:bg-accent hover:text-ink-900 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {submitting ? 'Signing in…' : 'Enter the studio'}
            </button>
          </form>
        </section>
      </div>

      <footer className="border-t border-rule">
        <div className="mx-auto flex max-w-editorial items-center justify-between px-8 py-5 font-mono text-[0.6rem] uppercase tracking-widest text-parchment-dim">
          <span>SUPERVOID Entangled</span>
          <span>Locally hosted</span>
        </div>
      </footer>
    </div>
  );
}
