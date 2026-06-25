import { useState } from 'react';
import type { PublicHotspot, PublishedPage, PublishedPanel } from '../types/reader';
import { mediaUrl } from '../api/publicClient';
import { HotspotLayer } from './HotspotLayer';
import { VideoPlayer } from './VideoPlayer';

/** Real panel-by-panel cinematic framing from normalised panel coordinates.
 *
 * The page image is scaled and panned so the panel's focus rectangle (or the
 * panel rectangle itself) fills the letterbox, with a configurable transition.
 * Falls back gracefully to a full-page display when a page has no panels. */
export function CinematicStage({
  page,
  panelIndex,
  hotspotsVisible,
  onOpenHotspot,
}: {
  page: PublishedPage;
  panelIndex: number;
  hotspotsVisible: boolean;
  onOpenHotspot: (h: PublicHotspot) => void;
}) {
  const [failed, setFailed] = useState(false);
  const url = mediaUrl(page.image_path);
  const aspect = page.width && page.height ? page.width / page.height : 0.7;

  // Graceful fallback: no panels → show the whole page.
  if (page.panels.length === 0) {
    return (
      <div className="sv-letterbox relative flex w-full justify-center">
        <span className="absolute left-4 top-2 z-30 font-mono text-[0.54rem] uppercase tracking-widest text-parchment-shadow">
          Cinematic · full page (no panels)
        </span>
        <figure className="sv-page-plate relative" style={{ height: '78vh', aspectRatio: String(aspect) }}>
          {url && !failed ? (
            <img
              src={url}
              alt={page.alt_text ?? `Page ${page.page_number}`}
              className="h-full w-full object-contain"
              draggable={false}
              onError={() => setFailed(true)}
            />
          ) : (
            <PagePlaceholder page={page} />
          )}
          <HotspotLayer hotspots={page.hotspots} visible={hotspotsVisible} onOpen={onOpenHotspot} />
        </figure>
      </div>
    );
  }

  const panel: PublishedPanel =
    page.panels[Math.min(panelIndex, page.panels.length - 1)];

  const fx = panel.focus_x ?? panel.x;
  const fy = panel.focus_y ?? panel.y;
  const fw = panel.focus_width ?? panel.width;
  const fh = panel.focus_height ?? panel.height;
  const cx = fx + fw / 2;
  const cy = fy + fh / 2;
  // Contain the focus rect within the viewport (never crops panel content).
  const scale = 1 / Math.max(fw || 1, fh || 1);
  const dx = (0.5 - cx) * 100;
  const dy = (0.5 - cy) * 100;
  const duration = panel.transition === 'cut' ? 0 : panel.transition_duration_ms;
  const dissolve = panel.transition === 'fade' || panel.transition === 'dissolve';

  return (
    <div className="sv-letterbox relative flex w-full justify-center">
      <span className="absolute left-4 top-2 z-30 font-mono text-[0.54rem] uppercase tracking-widest text-parchment-shadow">
        Cinematic · panel {panel.panel_number}
      </span>
      <div
        className="relative overflow-hidden bg-ink-900"
        style={{ height: '78vh', aspectRatio: String(aspect) }}
        role="group"
        aria-roledescription="comic panel"
        aria-label={panel.alt_text ?? panel.caption ?? `Panel ${panel.panel_number}`}
      >
        {/* The transformed page layer (image + panel hotspots pan/zoom together). */}
        <div
          className="absolute inset-0"
          style={{
            transform: `scale(${scale}) translate(${dx}%, ${dy}%)`,
            transformOrigin: 'center center',
            transition: `transform ${duration}ms ease, opacity ${duration}ms ease`,
            opacity: dissolve ? 0.999 : 1,
          }}
          key={dissolve ? panel.id : undefined}
        >
          {url && !failed ? (
            <img
              src={url}
              alt={page.alt_text ?? `Page ${page.page_number}`}
              className="h-full w-full object-contain"
              draggable={false}
              onError={() => setFailed(true)}
            />
          ) : (
            <PagePlaceholder page={page} />
          )}
          <HotspotLayer
            hotspots={panel.hotspots}
            visible={hotspotsVisible}
            onOpen={onOpenHotspot}
          />
        </div>

        {/* Panel caption + accessibility live region. */}
        {panel.caption && (
          <p
            className="absolute inset-x-0 bottom-0 z-30 bg-gradient-to-t from-ink-900/90 to-transparent px-6 pb-5 pt-10 text-center font-serif text-lg italic text-parchment"
            aria-live="polite"
          >
            {panel.caption}
          </p>
        )}
        <span className="sr-only" aria-live="polite">
          Panel {panel.panel_number} of {page.panels.length}.{' '}
          {panel.alt_text ?? panel.caption ?? ''}
        </span>

        {/* Panel-level video / audio. */}
        {panel.video && (
          <div className="absolute right-3 top-3 z-30 w-44 border border-rule bg-ink-900/80 shadow-lg">
            <VideoPlayer asset={panel.video} className="aspect-video w-full bg-black" />
          </div>
        )}
        {panel.audio_track && (
          <audio
            className="absolute bottom-3 right-3 z-30 h-8 w-44"
            src={mediaUrl(panel.audio_track.file_path) ?? undefined}
            controls
            loop={panel.audio_track.loop}
          />
        )}
      </div>
    </div>
  );
}

function PagePlaceholder({ page }: { page: PublishedPage }) {
  return (
    <div className="grid h-full w-full place-items-center bg-gradient-to-b from-ink-700 to-ink-900">
      <div className="text-center">
        <p className="font-serif text-2xl italic text-parchment-shadow">
          {page.alt_text ?? 'The Silent Workshop'}
        </p>
        <p className="mt-2 font-mono text-[0.6rem] uppercase tracking-widest text-parchment-shadow/70">
          Page {String(page.page_number).padStart(2, '0')}
        </p>
      </div>
    </div>
  );
}
