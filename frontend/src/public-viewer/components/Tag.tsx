import type { ReactNode } from 'react';

export function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="border border-rule px-2 py-0.5 font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
      {children}
    </span>
  );
}
