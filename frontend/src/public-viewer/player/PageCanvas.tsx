import { useState } from 'react';
import type { PublicHotspot, PublishedPage, ReaderMode } from '../types/reader';
import { mediaUrl } from '../api/publicClient';
import { HotspotLayer } from './HotspotLayer';
import { VideoPlayer } from './VideoPlayer';

type FitMode = 'width' | 'height' | 'none';

function PageFigure({
  page,
  fit,
  zoom,
  hotspotsVisible,
  onOpenHotspot,
}: {
  page: PublishedPage;
  fit: FitMode;
  zoom: number;
  hotspotsVisible: boolean;
  onOpenHotspot: (h: PublicHotspot) => void;
}) {
  const [failed, setFailed] = useState(false);
  const url = mediaUrl(page.image_path);
  const ratio = page.width && page.height ? page.width / page.height : 0.7;

  const sizing =
    fit === 'width'
      ? 'w-full h-auto'
      : fit === 'height'
        ? 'h-[82vh] w-auto'
        : 'max-h-[85vh] w-auto';

  return (
    <figure
      className="sv-page-plate sv-page-fade relative"
      style={zoom !== 1 ? { transform: `scale(${zoom})`, transformOrigin: 'top center' } : undefined}
    >
      {url && !failed ? (
        <img
          src={url}
          alt={page.alt_text ?? `Page ${page.page_number}`}
          className={`block select-none ${sizing}`}
          draggable={false}
          onError={() => setFailed(true)}
        />
      ) : (
        <div
          className={`grid place-items-center bg-gradient-to-b from-ink-700 to-ink-900 ${fit === 'width' ? 'w-full' : 'h-[82vh]'}`}
          style={{ aspectRatio: String(ratio) }}
        >
          <div className="text-center">
            <p className="font-serif text-2xl italic text-parchment-shadow">
              {page.alt_text ?? 'The Silent Workshop'}
            </p>
            <p className="mt-2 font-mono text-[0.6rem] uppercase tracking-widest text-parchment-shadow/70">
              Page {String(page.page_number).padStart(2, '0')}
            </p>
          </div>
        </div>
      )}

      <HotspotLayer
        hotspots={page.hotspots}
        visible={hotspotsVisible}
        onOpen={onOpenHotspot}
      />

      {page.video_overlay && (
        <div
          className="absolute bottom-3 right-3 z-30 w-48 border border-rule bg-ink-900/80 shadow-lg sm:w-56"
          onClick={(e) => e.stopPropagation()}
        >
          <p className="border-b border-rule px-2 py-1 font-mono text-[0.5rem] uppercase tracking-widest text-parchment-dim">
            {page.video_overlay.title}
          </p>
          <VideoPlayer asset={page.video_overlay} className="aspect-video w-full bg-black" />
        </div>
      )}
    </figure>
  );
}

export function PageCanvas({
  pages,
  mode,
  pageIndex,
  fit,
  zoom,
  hotspotsVisible,
  onOpenHotspot,
}: {
  pages: PublishedPage[];
  mode: ReaderMode;
  pageIndex: number;
  fit: FitMode;
  zoom: number;
  hotspotsVisible: boolean;
  onOpenHotspot: (h: PublicHotspot) => void;
}) {
  if (pages.length === 0) {
    return (
      <p className="font-serif text-lg italic text-parchment-dim">
        This chapter has no pages yet.
      </p>
    );
  }

  const figure = (page: PublishedPage, fitOverride?: FitMode) => (
    <PageFigure
      key={page.id}
      page={page}
      fit={fitOverride ?? fit}
      zoom={zoom}
      hotspotsVisible={hotspotsVisible}
      onOpenHotspot={onOpenHotspot}
    />
  );

  if (mode === 'scroll') {
    return (
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-6 pb-24">
        {pages.map((page) => figure(page, 'width'))}
      </div>
    );
  }

  if (mode === 'double') {
    const left = pages[pageIndex];
    const right = pages[pageIndex + 1];
    return (
      <div className="flex items-start justify-center gap-1">
        {left && figure(left, 'height')}
        {right && figure(right, 'height')}
      </div>
    );
  }

  if (mode === 'cinematic') {
    return (
      <div className="sv-letterbox relative flex w-full justify-center">
        <span className="absolute left-4 top-2 z-30 font-mono text-[0.54rem] uppercase tracking-widest text-parchment-shadow">
          Cinematic · preview
        </span>
        {figure(pages[pageIndex], 'height')}
      </div>
    );
  }

  // single
  return <div className="flex justify-center">{figure(pages[pageIndex])}</div>;
}
