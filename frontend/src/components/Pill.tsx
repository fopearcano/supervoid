import type { ReactNode } from 'react';

type Tone = 'muted' | 'accent' | 'live' | 'signal';

const TONE: Record<Tone, string> = {
  muted: 'border-rule text-parchment-dim',
  accent: 'border-accent/50 text-accent',
  live: 'border-accent text-parchment',
  signal: 'border-signal/40 text-signal/90',
};

/** A small, restrained mono chip for divisions, media, canon and statuses. */
export function Pill({
  children,
  tone = 'muted',
}: {
  children: ReactNode;
  tone?: Tone;
}) {
  return (
    <span
      className={`inline-flex items-center border ${TONE[tone]} px-2 py-0.5 font-mono text-[0.58rem] uppercase tracking-widest`}
    >
      {children}
    </span>
  );
}
