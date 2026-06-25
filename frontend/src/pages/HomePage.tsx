import { ThemeToggle } from '@/components/ThemeToggle';

// Community / external links. Placeholders — replace with the real invites and
// channels. They open in a new tab; "Members" enters the private sign-in.
const COMMUNITY_LINKS: { label: string; href: string }[] = [
  { label: 'Discord', href: 'https://discord.gg/supervoid' },
  { label: 'Telegram news', href: 'https://t.me/supervoid' },
];

interface HomePageProps {
  onEnterMembers: () => void;
}

export function HomePage({ onEnterMembers }: HomePageProps) {
  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-ink-900">
      <header className="flex items-center justify-between px-6 py-5">
        <span className="font-mono text-[0.6rem] uppercase tracking-widest text-parchment-dim">
          SUPERVOID Entangled
        </span>
        <ThemeToggle />
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        {/* kicker — a slightly torn sticker sitting on the title */}
        <span className="-rotate-2 select-none bg-accent px-3 py-1 font-mono text-[0.8rem] font-bold uppercase tracking-[0.2em] text-ink-900">
          {"I've got a mental"}
        </span>

        <h1
          className="mt-4 font-sans font-black uppercase leading-[0.82] tracking-tighter text-parchment text-[clamp(3.25rem,16vw,12rem)]"
          style={{ textShadow: '5px 5px 0 rgb(var(--c-accent-deep))' }}
        >
          SUPER<span className="text-accent">VOID</span>
        </h1>

        <p className="mt-5 font-mono text-[0.72rem] uppercase tracking-[0.5em] text-parchment-muted">
          Publishing
        </p>

        <p className="mt-8 max-w-md text-parchment-muted">
          An independent transmedia studio. Stories, comics, screen and sound —
          made loud, kept ours.
        </p>
      </main>

      <footer className="flex flex-wrap items-center justify-center gap-3 px-6 py-9">
        {COMMUNITY_LINKS.map((link) => (
          <a
            key={link.label}
            href={link.href}
            target="_blank"
            rel="noreferrer"
            className="border border-rule px-4 py-2 font-mono text-[0.7rem] uppercase tracking-widest text-parchment-muted transition-colors hover:border-accent hover:text-parchment"
          >
            {link.label} ↗
          </a>
        ))}
        <button
          type="button"
          onClick={onEnterMembers}
          className="border border-accent px-4 py-2 font-mono text-[0.7rem] uppercase tracking-widest text-accent transition-colors hover:bg-accent hover:text-ink-900"
        >
          Members →
        </button>
      </footer>
    </div>
  );
}
