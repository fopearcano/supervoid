import { useEffect, useState } from 'react';
import { listWorks } from '../api/reader';
import type { PublishedWorkSummary } from '../types/reader';
import { ReaderShell } from '../layouts/ReaderShell';
import { WorkCard } from '../components/WorkCard';
import { Spinner } from '../components/Spinner';

export function LandingPage() {
  const [works, setWorks] = useState<PublishedWorkSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    listWorks()
      .then((data) => active && setWorks(data))
      .catch((err) => active && setError(err?.message ?? String(err)));
    return () => {
      active = false;
    };
  }, []);

  return (
    <ReaderShell>
      <div className="border-b border-rule pb-10">
        <p className="label-eyebrow">Published works</p>
        <h1 className="mt-4 max-w-2xl font-serif text-5xl leading-[1.05] text-parchment">
          The SUPERVOID Reading Room
        </h1>
        <p className="mt-5 max-w-xl text-base leading-relaxed text-parchment-muted/80">
          An archive of graphic novels published by SUPERVOID — read in a quiet,
          cinematic viewer with music, motion, and curated annotations.
        </p>
      </div>

      <div className="mt-12">
        {error && (
          <p className="font-mono text-sm text-signal">
            Could not load works — {error}
          </p>
        )}
        {!works && !error && <Spinner label="Loading works" />}
        {works && works.length === 0 && (
          <p className="font-serif text-lg italic text-parchment-dim">
            No works have been published yet.
          </p>
        )}
        {works && works.length > 0 && (
          <div className="grid grid-cols-2 gap-x-8 gap-y-12 sm:grid-cols-3 lg:grid-cols-4">
            {works.map((work) => (
              <WorkCard key={work.id} work={work} />
            ))}
          </div>
        )}
      </div>
    </ReaderShell>
  );
}
