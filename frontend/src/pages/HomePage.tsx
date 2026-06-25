import { useState } from 'react';
import { ThemeToggle } from '@/components/ThemeToggle';
import { SignInModal } from '@/components/SignInModal';

// Community / external links. Placeholders — replace with the real invites and
// channels. They open in a new tab; "Members" opens the sign-in.
const COMMUNITY_LINKS: { label: string; href: string }[] = [
  { label: 'Discord', href: 'https://discord.gg/supervoid' },
  { label: 'Telegram news', href: 'https://t.me/supervoid' },
];

const MARQUEE = "✶ SUPERVOID ✶ I'VE GOT A MENTAL ✶ MADE LOUD, KEPT OURS ✶ DIY OR DIE ";

export function HomePage() {
  const [signInOpen, setSignInOpen] = useState(false);

  return (
    <div className="sv-scanlines relative flex min-h-screen flex-col overflow-hidden bg-ink-900">
      {/* punk marquee band */}
      <div className="relative z-10 overflow-hidden border-b-2 border-ink-900 bg-accent">
        <div className="sv-marquee py-1.5">
          {[0, 1].map((i) => (
            <span
              key={i}
              className="px-2 font-mono text-[0.72rem] font-bold uppercase tracking-[0.3em] text-ink-900"
            >
              {MARQUEE.repeat(6)}
            </span>
          ))}
        </div>
      </div>

      <header className="relative z-10 flex items-center justify-between px-6 py-5">
        <span className="font-mono text-[0.6rem] uppercase tracking-widest text-parchment-dim">
          SUPERVOID Entangled
        </span>
        <ThemeToggle />
      </header>

      <main className="relative z-10 flex flex-1 flex-col items-center justify-center px-6 text-center">
        {/* a scattered sticker, for the zine feel */}
        <span className="pointer-events-none absolute right-[8%] top-[6%] hidden rotate-6 select-none border border-parchment-dim px-2 py-1 font-mono text-[0.6rem] uppercase tracking-widest text-parchment-dim sm:block">
          Est. MMXXVI
        </span>

        {/* enlarged punk kicker */}
        <span
          className="-rotate-3 select-none font-sans font-black uppercase leading-[0.85] tracking-tight text-accent text-[clamp(2rem,7vw,4.5rem)]"
          style={{ textShadow: '3px 3px 0 rgb(var(--c-ink-900))' }}
        >
          {"I've got a mental"}
        </span>

        <h1
          className="mt-2 font-sans font-black uppercase leading-[0.8] tracking-tighter text-parchment text-[clamp(3.5rem,17vw,13rem)]"
          style={{
            textShadow:
              '5px 5px 0 rgb(var(--c-accent-deep)), 10px 10px 0 rgb(var(--c-ink-700))',
          }}
        >
          SUPER<span className="text-accent">VOID</span>
        </h1>

        {/* accent slash under the title */}
        <span aria-hidden className="mt-3 h-1.5 w-40 max-w-[60%] -skew-x-12 bg-accent" />

        <p className="mt-6 max-w-md text-[1.05rem] text-parchment-muted">
          An independent transmedia studio. Stories, comics, screen and sound —
          made loud, kept ours.
        </p>
      </main>

      <footer className="relative z-10 flex flex-wrap items-center justify-center gap-3 px-6 py-9">
        {COMMUNITY_LINKS.map((link) => (
          <a
            key={link.label}
            href={link.href}
            target="_blank"
            rel="noreferrer"
            className="border-2 border-rule px-5 py-2.5 font-mono text-[0.72rem] font-bold uppercase tracking-widest text-parchment-muted transition-colors hover:border-accent hover:text-parchment"
          >
            {link.label} ↗
          </a>
        ))}
        <button
          type="button"
          onClick={() => setSignInOpen(true)}
          className="bg-accent px-6 py-2.5 font-mono text-[0.72rem] font-bold uppercase tracking-widest text-ink-900 transition-opacity hover:opacity-90"
        >
          Members →
        </button>
      </footer>

      {signInOpen && <SignInModal onClose={() => setSignInOpen(false)} />}
    </div>
  );
}
