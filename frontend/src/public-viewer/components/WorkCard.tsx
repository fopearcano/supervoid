import { Link, readerPaths } from '../router';
import { CoverImage } from './CoverImage';
import { Tag } from './Tag';
import type { PublishedWorkSummary } from '../types/reader';

export function WorkCard({ work }: { work: PublishedWorkSummary }) {
  return (
    <Link
      to={readerPaths.work(work.slug)}
      className="group flex flex-col"
      aria-label={`Open ${work.title}`}
    >
      <div className="relative aspect-[2/3] overflow-hidden border border-rule bg-ink-700">
        <CoverImage
          src={work.cover_image}
          alt={work.title}
          className="transition-transform duration-700 group-hover:scale-[1.03]"
        />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-ink-900/70 via-transparent to-transparent" />
        <span className="absolute bottom-3 right-3 font-mono text-[0.58rem] uppercase tracking-widest text-parchment opacity-0 transition-opacity duration-300 group-hover:opacity-100">
          Read →
        </span>
      </div>

      <h3 className="mt-4 font-serif text-xl leading-tight text-parchment transition-colors group-hover:text-accent">
        {work.title}
      </h3>
      {work.subtitle && (
        <p className="mt-1 font-serif text-sm italic text-parchment-dim">
          {work.subtitle}
        </p>
      )}
      {work.public_synopsis && (
        <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-parchment-muted/80">
          {work.public_synopsis}
        </p>
      )}
      {work.tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {work.tags.slice(0, 4).map((tag) => (
            <Tag key={tag}>{tag}</Tag>
          ))}
        </div>
      )}
    </Link>
  );
}
