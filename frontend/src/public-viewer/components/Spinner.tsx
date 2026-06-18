export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-parchment-dim">
      <span className="h-3 w-3 animate-spin rounded-full border border-rule border-t-accent" />
      <span className="font-mono text-[0.66rem] uppercase tracking-widest">{label}</span>
    </div>
  );
}
