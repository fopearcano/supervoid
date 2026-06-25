import { useEffect, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import type {
  PublicHotspot,
  PublicMediaAsset,
  PublishedChapter,
  PublishedPage,
  PublishedVolume,
  PublishedWorkDetail,
  ReaderMode,
} from '../types/reader';
import { useFullscreen } from '../hooks/useFullscreen';
import { useKeyboard } from '../hooks/useKeyboard';
import { EnterOverlay } from '../components/EnterOverlay';
import { Spinner } from '../components/Spinner';
import { PageCanvas } from './PageCanvas';
import { ReaderControls } from './ReaderControls';
import { HotspotDetail } from './HotspotLayer';
import { VideoPlayer } from './VideoPlayer';

type FitMode = 'width' | 'height' | 'none';

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

export interface GraphicNovelViewerProps {
  work: PublishedWorkDetail;
  volume: PublishedVolume;
  chapter: PublishedChapter | null;
  chapterId: string;
  pages: PublishedPage[];
  pagesLoading: boolean;
  entered: boolean;
  startMuted: boolean;
  onEnter: (withSound: boolean) => void;
  onExit: () => void;
  onNavigateChapter: (volumeId: string, chapterId: string) => void;
}

export function GraphicNovelViewer(props: GraphicNovelViewerProps) {
  const { work, volume, chapter, chapterId, pages, entered } = props;

  const containerRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pointerStart = useRef<{ x: number; y: number } | null>(null);
  const suppressClick = useRef(false);
  const { isFullscreen, toggleFullscreen } = useFullscreen(containerRef);

  const [mode, setMode] = useState<ReaderMode>('single');
  const [pageIndex, setPageIndex] = useState(0);
  const [panelIndex, setPanelIndex] = useState(0);
  const [fit, setFit] = useState<FitMode>('height');
  const [zoom, setZoom] = useState(1);
  const [chromeVisible, setChromeVisible] = useState(true);
  const [hotspotsVisible, setHotspotsVisible] = useState(true);
  const [activeHotspot, setActiveHotspot] = useState<PublicHotspot | null>(null);
  const [showIntro, setShowIntro] = useState(true);
  const [scrollProgress, setScrollProgress] = useState(0);

  // Reset per-chapter view state when the chapter changes.
  useEffect(() => {
    setPageIndex(0);
    setPanelIndex(0);
    setShowIntro(true);
    setActiveHotspot(null);
    scrollRef.current?.scrollTo({ top: 0 });
  }, [chapterId]);

  // Start each cinematic session (mode switch) at the first panel.
  useEffect(() => {
    setPanelIndex(0);
  }, [mode]);

  const summaries = volume.chapters;
  const chapterIdx = summaries.findIndex((c) => c.id === chapterId);
  const chapterTitle =
    chapter?.title ?? summaries[chapterIdx]?.title ?? 'Chapter';

  // Music: most specific available level wins.
  const currentPage: PublishedPage | undefined = pages[pageIndex];
  const pageTrack = mode === 'scroll' ? null : currentPage?.music_track ?? null;
  const musicTrack: PublicMediaAsset | null =
    pageTrack ??
    chapter?.music_track ??
    volume.music_track ??
    work.music_track ??
    null;

  // Intro video: chapter intro, or the work intro on the very first chapter.
  const firstChapterOfWork =
    work.volumes[0]?.chapters[0]?.id === chapterId;
  const introVideo =
    chapter?.video_intro ?? (firstChapterOfWork ? work.video_intro : null);
  const introActive = entered && showIntro && Boolean(introVideo);

  const scrollByViewport = (dir: number) =>
    scrollRef.current?.scrollBy({
      top: dir * window.innerHeight * 0.85,
      behavior: 'smooth',
    });

  const next = () => {
    if (mode === 'scroll') return scrollByViewport(1);
    if (mode === 'cinematic') {
      const panels = pages[pageIndex]?.panels ?? [];
      if (panelIndex + 1 < panels.length) return setPanelIndex((i) => i + 1);
      if (pageIndex + 1 < pages.length) {
        setPageIndex((i) => i + 1);
        return setPanelIndex(0);
      }
      const nx = summaries[chapterIdx + 1];
      if (nx) props.onNavigateChapter(volume.id, nx.id);
      return;
    }
    const step = mode === 'double' ? 2 : 1;
    if (pageIndex + step < pages.length) {
      setPageIndex((i) => Math.min(i + step, pages.length - 1));
    } else {
      const nx = summaries[chapterIdx + 1];
      if (nx) props.onNavigateChapter(volume.id, nx.id);
    }
  };

  const prev = () => {
    if (mode === 'scroll') return scrollByViewport(-1);
    if (mode === 'cinematic') {
      if (panelIndex > 0) return setPanelIndex((i) => i - 1);
      if (pageIndex > 0) {
        const previousPanels = pages[pageIndex - 1]?.panels ?? [];
        setPageIndex((i) => i - 1);
        return setPanelIndex(Math.max(previousPanels.length - 1, 0));
      }
      const pv = summaries[chapterIdx - 1];
      if (pv) props.onNavigateChapter(volume.id, pv.id);
      return;
    }
    const step = mode === 'double' ? 2 : 1;
    if (pageIndex - step >= 0) {
      setPageIndex((i) => Math.max(i - step, 0));
    } else if (pageIndex > 0) {
      setPageIndex(0);
    } else {
      const pv = summaries[chapterIdx - 1];
      if (pv) props.onNavigateChapter(volume.id, pv.id);
    }
  };

  const onSetFit = (f: FitMode) => {
    setFit(f);
    setZoom(1);
  };
  const onZoom = (delta: number) => {
    setFit('none');
    setZoom((z) => clamp(Number((z + delta).toFixed(2)), 0.4, 3));
  };

  useKeyboard(
    {
      ArrowRight: next,
      ArrowLeft: prev,
      PageDown: next,
      PageUp: prev,
      ' ': (e) => {
        e.preventDefault();
        next();
      },
      f: toggleFullscreen,
      F: toggleFullscreen,
      h: () => setChromeVisible((v) => !v),
      H: () => setChromeVisible((v) => !v),
      '+': () => onZoom(0.15),
      '=': () => onZoom(0.15),
      '-': () => onZoom(-0.15),
      '1': () => setMode('single'),
      '2': () => setMode('double'),
      '3': () => setMode('scroll'),
      '4': () => setMode('cinematic'),
      Escape: () => {
        if (activeHotspot) setActiveHotspot(null);
        else if (!chromeVisible) setChromeVisible(true);
      },
    },
    entered && !introActive,
  );

  // Pager label + progress.
  let progress = 0;
  let pageLabel = '';
  if (mode === 'scroll') {
    progress = scrollProgress;
    pageLabel = `${pages.length} pp`;
  } else if (mode === 'cinematic') {
    const panels = pages[pageIndex]?.panels ?? [];
    if (panels.length) {
      progress = pages.length
        ? (pageIndex + (panelIndex + 1) / panels.length) / pages.length
        : 0;
      pageLabel = `p${pageIndex + 1} · panel ${panelIndex + 1}/${panels.length}`;
    } else {
      progress = pages.length ? (pageIndex + 1) / pages.length : 0;
      pageLabel = `${pageIndex + 1} / ${pages.length}`;
    }
  } else if (mode === 'double') {
    const last = Math.min(pageIndex + 2, pages.length);
    progress = pages.length ? last / pages.length : 0;
    pageLabel = `${pageIndex + 1}–${last} / ${pages.length}`;
  } else {
    progress = pages.length ? (pageIndex + 1) / pages.length : 0;
    pageLabel = `${pageIndex + 1} / ${pages.length}`;
  }

  const onPointerDown = (e: ReactPointerEvent) => {
    pointerStart.current = { x: e.clientX, y: e.clientY };
  };
  const onPointerUp = (e: ReactPointerEvent) => {
    const start = pointerStart.current;
    pointerStart.current = null;
    if (!start || mode === 'scroll') return;
    const dx = e.clientX - start.x;
    const dy = e.clientY - start.y;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) {
      suppressClick.current = true;
      if (dx < 0) next();
      else prev();
    }
  };
  const onAreaClick = () => {
    if (suppressClick.current) {
      suppressClick.current = false;
      return;
    }
    setChromeVisible((v) => !v);
  };

  return (
    <div
      ref={containerRef}
      className="sv-reader-root fixed inset-0 z-30 overflow-hidden bg-ink-900 text-parchment"
    >
      <div
        ref={scrollRef}
        className={`absolute inset-0 overflow-auto px-2 ${mode === 'scroll' ? 'sv-scroll-column pt-16 pb-10' : 'grid place-items-center pt-16 pb-20'}`}
        onPointerDown={onPointerDown}
        onPointerUp={onPointerUp}
        onClick={onAreaClick}
        onScroll={(e) => {
          if (mode !== 'scroll') return;
          const el = e.currentTarget;
          const max = el.scrollHeight - el.clientHeight;
          setScrollProgress(max > 0 ? el.scrollTop / max : 0);
        }}
      >
        {props.pagesLoading && pages.length === 0 ? (
          <Spinner label="Loading pages" />
        ) : (
          <PageCanvas
            pages={pages}
            mode={mode}
            pageIndex={pageIndex}
            panelIndex={panelIndex}
            fit={fit}
            zoom={zoom}
            hotspotsVisible={hotspotsVisible}
            onOpenHotspot={setActiveHotspot}
          />
        )}
      </div>

      <ReaderControls
        chromeVisible={chromeVisible && entered && !introActive}
        workTitle={work.title}
        chapterTitle={chapterTitle}
        onExit={props.onExit}
        mode={mode}
        onMode={setMode}
        pageLabel={pageLabel}
        progress={progress}
        onPrev={prev}
        onNext={next}
        fit={fit}
        zoom={zoom}
        onSetFit={onSetFit}
        onZoom={onZoom}
        hotspotsVisible={hotspotsVisible}
        onToggleHotspots={() => setHotspotsVisible((v) => !v)}
        isFullscreen={isFullscreen}
        onToggleFullscreen={toggleFullscreen}
        onHideChrome={() => setChromeVisible(false)}
        volumes={work.volumes}
        volumeId={volume.id}
        chapters={summaries}
        chapterId={chapterId}
        onSelectVolume={(v) => {
          const first = v.chapters[0];
          if (first) props.onNavigateChapter(v.id, first.id);
        }}
        onSelectChapter={(id) => props.onNavigateChapter(volume.id, id)}
        audioTrack={musicTrack}
        audioEnabled={entered}
        audioStartMuted={props.startMuted}
      />

      {/* Reveal chrome affordance when hidden */}
      {!chromeVisible && entered && !introActive && (
        <button
          type="button"
          onClick={() => setChromeVisible(true)}
          className="absolute right-3 top-3 z-40 font-mono text-[0.54rem] uppercase tracking-widest text-parchment-shadow hover:text-parchment"
        >
          Show interface
        </button>
      )}

      {introActive && introVideo && (
        <div className="absolute inset-0 z-40 grid place-items-center bg-ink-900 p-6">
          <div className="w-full max-w-4xl">
            <VideoPlayer
              asset={introVideo}
              autoPlay
              className="aspect-video w-full bg-black"
            />
            <div className="mt-3 text-right">
              <button
                type="button"
                onClick={() => setShowIntro(false)}
                className="button-accent"
              >
                Skip intro →
              </button>
            </div>
          </div>
        </div>
      )}

      {activeHotspot && (
        <HotspotDetail
          hotspot={activeHotspot}
          onClose={() => setActiveHotspot(null)}
        />
      )}

      {!entered && (
        <EnterOverlay
          title={work.title}
          subtitle={work.subtitle}
          hasAudio={Boolean(musicTrack)}
          onEnter={props.onEnter}
        />
      )}
    </div>
  );
}
