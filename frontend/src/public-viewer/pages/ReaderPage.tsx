import { useEffect, useState } from 'react';
import { getWork, listChapters, listPages } from '../api/reader';
import type {
  PublishedChapter,
  PublishedPage,
  PublishedWorkDetail,
} from '../types/reader';
import { GraphicNovelViewer } from '../player/GraphicNovelViewer';
import { Spinner } from '../components/Spinner';
import { Link, navigate, readerPaths } from '../router';

export function ReaderPage({
  slug,
  volumeId,
  chapterId,
}: {
  slug: string;
  volumeId: string;
  chapterId: string;
}) {
  const [work, setWork] = useState<PublishedWorkDetail | null>(null);
  const [chapters, setChapters] = useState<PublishedChapter[]>([]);
  const [pages, setPages] = useState<PublishedPage[]>([]);
  const [pagesLoading, setPagesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [entered, setEntered] = useState(false);
  const [startMuted, setStartMuted] = useState(false);

  // The work (also drives nav + the per-work Enter overlay).
  useEffect(() => {
    let active = true;
    setWork(null);
    setEntered(false);
    setError(null);
    getWork(slug)
      .then((w) => active && setWork(w))
      .catch((e) => active && setError(e?.message ?? String(e)));
    return () => {
      active = false;
    };
  }, [slug]);

  // Full chapters of the current volume (for chapter-level music/intro).
  useEffect(() => {
    let active = true;
    listChapters(volumeId)
      .then((c) => active && setChapters(c))
      .catch(() => active && setChapters([]));
    return () => {
      active = false;
    };
  }, [volumeId]);

  // Pages of the current chapter (with hotspots + resolved media).
  useEffect(() => {
    let active = true;
    setPagesLoading(true);
    listPages(chapterId)
      .then((p) => {
        if (active) {
          setPages(p);
          setPagesLoading(false);
        }
      })
      .catch(() => {
        if (active) {
          setPages([]);
          setPagesLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [chapterId]);

  const volume = work?.volumes.find((v) => v.id === volumeId);

  // An unknown volume slug -> fall back to the work detail.
  useEffect(() => {
    if (work && !volume) navigate(readerPaths.work(slug));
  }, [work, volume, slug]);

  if (error) {
    return (
      <div className="grid min-h-screen place-items-center bg-ink-900 px-6 text-center">
        <div>
          <p className="font-mono text-sm text-signal">Could not open this reader.</p>
          <p className="mt-2 text-parchment-dim">{error}</p>
          <Link
            to={readerPaths.work(slug)}
            className="mt-6 inline-block font-mono text-[0.62rem] uppercase tracking-widest text-accent hover:underline"
          >
            ← Back to the work
          </Link>
        </div>
      </div>
    );
  }

  if (!work || !volume) {
    return (
      <div className="grid min-h-screen place-items-center bg-ink-900">
        <Spinner label="Opening reader" />
      </div>
    );
  }

  const chapter = chapters.find((c) => c.id === chapterId) ?? null;

  return (
    <GraphicNovelViewer
      work={work}
      volume={volume}
      chapter={chapter}
      chapterId={chapterId}
      pages={pages}
      pagesLoading={pagesLoading}
      entered={entered}
      startMuted={startMuted}
      onEnter={(withSound) => {
        setStartMuted(!withSound);
        setEntered(true);
      }}
      onExit={() => navigate(readerPaths.work(slug))}
      onNavigateChapter={(vId, cId) => navigate(readerPaths.read(slug, vId, cId))}
    />
  );
}
