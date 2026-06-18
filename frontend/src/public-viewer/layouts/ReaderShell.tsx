import type { ReactNode } from 'react';
import { Wordmark } from '../components/Wordmark';

/** Chrome for the non-immersive public pages (landing, work detail). */
export function ReaderShell({ children }: { children: ReactNode }) {
  return (
    <div className="sv-reader-root flex min-h-screen flex-col text-parchment">
      <header className="border-b border-rule">
        <div className="mx-auto flex w-full max-w-editorial items-center justify-between px-6 py-5">
          <Wordmark subtitle="Reader" />
          <span className="font-mono text-[0.56rem] uppercase tracking-[0.28em] text-parchment-shadow">
            Public Archive
          </span>
        </div>
      </header>

      <main className="mx-auto w-full max-w-editorial flex-1 px-6 py-12">
        {children}
      </main>

      <footer className="border-t border-rule">
        <div className="mx-auto w-full max-w-editorial px-6 py-8">
          <p className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-shadow">
            SUPERVOID ENTANGLED · Publishing — public reading room
          </p>
          <p className="mt-2 max-w-prose text-xs leading-relaxed text-parchment-shadow/70">
            A curated, public selection of SUPERVOID graphic novels. Editorial,
            production, and rights data live in the private system and are never
            exposed here.
          </p>
        </div>
      </footer>
    </div>
  );
}
