import { Link, readerPaths } from '../router';

/** The SUPERVOID public wordmark — links back to the reader landing. */
export function Wordmark({ subtitle = 'Archive' }: { subtitle?: string }) {
  return (
    <Link to={readerPaths.landing()} className="group inline-flex items-baseline gap-3">
      <span className="font-mono text-sm uppercase tracking-[0.34em] text-parchment transition-colors group-hover:text-accent">
        SUPERVOID
      </span>
      <span className="font-mono text-[0.58rem] uppercase tracking-[0.3em] text-parchment-dim">
        {subtitle}
      </span>
    </Link>
  );
}
