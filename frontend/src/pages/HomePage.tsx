import { useState } from 'react';
import { SignInModal } from '@/components/SignInModal';

// Community / external links. Placeholders — replace with the real shop, invite
// and channel URLs. They open in a new tab; "Members" opens the sign-in.
const COMMUNITY_LINKS: { label: string; href: string }[] = [
  { label: 'Bookshop', href: 'https://bookshop.org' },
  { label: 'Discord', href: 'https://discord.gg/supervoid' },
  { label: 'Telegram news', href: 'https://t.me/supervoid' },
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
        <span className="font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim">
          SUPERVOID Entangled
        </span>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-8 text-center">
        {/* kicker — classic serif, sitting center-left over the title */}
        <span className="ml-[18vw] select-none self-start font-serif italic leading-none text-accent text-[clamp(1.25rem,4vw,2.5rem)]">
          {'I’ve got a mental'}
        </span>

        <h1 className="-mt-1 font-serif leading-[0.85] tracking-tight text-parchment text-[clamp(3.5rem,17vw,13rem)]">
          SUPER<span className="text-accent">VOID</span>
        </h1>
      </main>

      <footer className="flex flex-wrap items-center justify-center gap-3 px-8 py-10">
        {COMMUNITY_LINKS.map((link) => (
          <a
            key={link.label}
            href={link.href}
            target="_blank"
            rel="noreferrer"
            className="border border-rule px-4 py-2 font-mono text-[0.66rem] uppercase tracking-widest text-parchment-muted transition-colors hover:border-accent hover:text-parchment"
          >
            {link.label} ↗
          </a>
        ))}
        <button
          type="button"
          onClick={() => setSignInOpen(true)}
          className="border border-accent px-5 py-2 font-mono text-[0.66rem] uppercase tracking-widest text-accent transition-colors hover:bg-accent hover:text-ink-900"
        >
          Members →
        </button>
      </footer>

      {signInOpen && <SignInModal onClose={() => setSignInOpen(false)} />}
    </div>
  );
}
