import { useState } from 'react';
import { SignInModal } from '@/components/SignInModal';

// External community links (open in a new tab). The Bookshop is an internal
// public page (/shop); "Members" opens the sign-in.
const COMMUNITY_LINKS: { label: string; href: string }[] = [
  { label: 'Discord', href: 'https://discord.gg/9ERtWkuft' },
];

// The scrolling top-bar phrase, repeated.
const MARQUEE = 'I’ve got a mental supervoid. · ';

export function HomePage() {
  const [signInOpen, setSignInOpen] = useState(false);

  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-ink-800">
      {/* slow scrolling top bar */}
      <div className="overflow-hidden border-b border-rule bg-ink-900">
        <div className="sv-marquee py-2">
          {[0, 1].map((i) => (
            <span
              key={i}
              className="px-1 font-mono text-[0.74rem] uppercase tracking-wider text-accent"
            >
              {MARQUEE.repeat(8)}
            </span>
          ))}
        </div>
      </div>

      <header className="flex items-center justify-between px-8 py-6">
        <span className="label-eyebrow">SUPERVOID Entangled</span>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-8 text-center">
        {/* kicker — Pinyon script, sitting center-left over the title */}
        <span className="ml-[14vw] select-none self-start font-script leading-[0.9] text-accent text-[clamp(1.75rem,5.5vw,3.5rem)]">
          {'I’ve got a mental'}
        </span>

        {/* wordmark — Cinzel deco caps */}
        <h1 className="font-display font-bold leading-[0.95] tracking-[0.015em] text-parchment text-[clamp(3rem,14vw,10rem)]">
          SUPER<span className="text-accent">VOID</span>
        </h1>
      </main>

      <footer className="flex flex-wrap items-center justify-center gap-3 px-8 py-10">
        <a href="/shop" className="button-outline">
          Bookshop →
        </a>
        {COMMUNITY_LINKS.map((link) => (
          <a
            key={link.label}
            href={link.href}
            target="_blank"
            rel="noreferrer"
            className="button-outline"
          >
            {link.label} ↗
          </a>
        ))}
        <button
          type="button"
          onClick={() => setSignInOpen(true)}
          className="button-accent"
        >
          Members →
        </button>
      </footer>

      {signInOpen && <SignInModal onClose={() => setSignInOpen(false)} />}
    </div>
  );
}
