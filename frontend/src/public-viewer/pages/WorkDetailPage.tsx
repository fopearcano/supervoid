import { useEffect, useState } from 'react';
import { getWork } from '../api/reader';
import type { PublishedWorkDetail } from '../types/reader';
import { ReaderShell } from '../layouts/ReaderShell';
import { CoverImage } from '../components/CoverImage';
import { Tag } from '../components/Tag';
import { Spinner } from '../components/Spinner';
import { Link, navigate, readerPaths } from '../router';

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

export function WorkDetailPage({ slug }: { slug: string }) {
  const [work, setWork] = useState<PublishedWorkDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setWork(null);
    setError(null);
    getWork(slug)
      .then((data) => active && setWork(data))
      .catch((err) => active && setError(err?.message ?? String(err)));
    return () => {
      active = false;
    };
  }, [slug]);

  const firstVolume = work?.volumes[0];
  const firstChapter = firstVolume?.chapters[0];
  const published = formatDate(work?.publication_date ?? null);

  return (
    <ReaderShell>
      <Link
        to={readerPaths.landing()}
        className="font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim hover:text-parchment"
      >
        ← All works
      </Link>

      {error && (
        <p className="mt-10 font-mono text-sm text-signal">
          Could not load this work — {error}
        </p>
      )}
      {!work && !error && (
        <div className="mt-10">
          <Spinner label="Loading" />
        </div>
      )}

      {work && (
        <div className="mt-8 grid gap-12 lg:grid-cols-[minmax(0,18rem)_1fr]">
          <div>
            <div className="aspect-[2/3] overflow-hidden border border-rule bg-ink-700">
              <CoverImage src={work.cover_image} alt={work.title} />
            </div>
            {firstChapter && (
              <button
                type="button"
                onClick={() =>
                  navigate(
                    readerPaths.read(work.slug, firstVolume!.id, firstChapter.id),
                  )
                }
                className="mt-5 w-full border border-accent px-4 py-3 font-mono text-[0.66rem] uppercase tracking-[0.28em] text-accent transition-colors hover:bg-accent hover:text-ink-900"
              >
                Begin reading
              </button>
            )}
          </div>

          <div>
            <p className="label-eyebrow">Graphic novel</p>
            <h1 className="mt-3 font-serif text-4xl leading-tight text-parchment">
              {work.title}
            </h1>
            {work.subtitle && (
              <p className="mt-2 font-serif text-xl italic text-parchment-dim">
                {work.subtitle}
              </p>
            )}

            <dl className="mt-6 flex flex-wrap gap-x-10 gap-y-3 font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim">
              {work.author_credit && (
                <div>
                  <dt className="text-parchment-shadow">Author</dt>
                  <dd className="mt-1 text-parchment-muted">{work.author_credit}</dd>
                </div>
              )}
              {work.artist_credit && (
                <div>
                  <dt className="text-parchment-shadow">Artist</dt>
                  <dd className="mt-1 text-parchment-muted">{work.artist_credit}</dd>
                </div>
              )}
              {published && (
                <div>
                  <dt className="text-parchment-shadow">Published</dt>
                  <dd className="mt-1 text-parchment-muted">{published}</dd>
                </div>
              )}
            </dl>

            {work.tags.length > 0 && (
              <div className="mt-5 flex flex-wrap gap-1.5">
                {work.tags.map((tag) => (
                  <Tag key={tag}>{tag}</Tag>
                ))}
              </div>
            )}

            {work.public_synopsis && (
              <p className="editorial-prose mt-7 max-w-chronicle">
                {work.public_synopsis}
              </p>
            )}

            <div className="mt-12">
              <p className="label-eyebrow">Contents</p>
              <div className="mt-5 divide-y divide-rule border-y border-rule">
                {work.volumes.map((volume) => (
                  <div key={volume.id} className="py-5">
                    <p className="font-serif text-lg text-parchment">
                      {volume.title}
                      <span className="ml-3 font-mono text-[0.58rem] uppercase tracking-widest text-parchment-shadow">
                        Vol. {volume.volume_number}
                      </span>
                    </p>
                    {volume.public_description && (
                      <p className="mt-1 text-sm text-parchment-muted/70">
                        {volume.public_description}
                      </p>
                    )}
                    <ul className="mt-3 space-y-1">
                      {volume.chapters.map((chapter) => (
                        <li key={chapter.id}>
                          <Link
                            to={readerPaths.read(work.slug, volume.id, chapter.id)}
                            className="group flex items-baseline justify-between gap-4 py-1 text-parchment-muted hover:text-parchment"
                          >
                            <span>
                              <span className="font-mono text-[0.62rem] text-parchment-shadow">
                                {String(chapter.chapter_number).padStart(2, '0')}
                              </span>{' '}
                              <span className="font-serif">{chapter.title}</span>
                            </span>
                            <span className="font-mono text-[0.56rem] uppercase tracking-widest text-parchment-shadow group-hover:text-accent">
                              {chapter.page_count} pp · Read →
                            </span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
                {work.volumes.length === 0 && (
                  <p className="py-5 font-serif italic text-parchment-dim">
                    Contents are being prepared.
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </ReaderShell>
  );
}
