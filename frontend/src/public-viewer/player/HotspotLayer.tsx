import type { PublicHotspot } from '../types/reader';
import { HOTSPOT_LABELS } from '../types/reader';
import { mediaUrl } from '../api/publicClient';
import { Icon } from './icons';
import { VideoPlayer } from './VideoPlayer';

/** Overlay of curated, public-only interactive regions on a page. */
export function HotspotLayer({
  hotspots,
  visible,
  onOpen,
}: {
  hotspots: PublicHotspot[];
  visible: boolean;
  onOpen: (hotspot: PublicHotspot) => void;
}) {
  if (hotspots.length === 0) return null;
  return (
    <div
      className={`pointer-events-none absolute inset-0 ${visible ? '' : 'sv-hotspots-hidden'}`}
    >
      {hotspots.map((hotspot) => (
        <button
          key={hotspot.id}
          type="button"
          className="sv-hotspot pointer-events-auto group"
          style={{
            left: `${hotspot.x}%`,
            top: `${hotspot.y}%`,
            width: `${hotspot.width}%`,
            height: `${hotspot.height}%`,
          }}
          onClick={(event) => {
            event.stopPropagation();
            onOpen(hotspot);
          }}
          aria-label={`${HOTSPOT_LABELS[hotspot.type]}: ${hotspot.title}`}
        >
          <span className="sv-hotspot__dot" />
          <span className="pointer-events-none absolute left-1/2 top-full mt-1.5 hidden -translate-x-1/2 whitespace-nowrap border border-rule bg-ink-900/90 px-2 py-0.5 font-mono text-[0.54rem] uppercase tracking-widest text-parchment group-hover:block">
            {HOTSPOT_LABELS[hotspot.type]} · {hotspot.title}
          </span>
        </button>
      ))}
    </div>
  );
}

/** The panel/modal that opens when a hotspot is activated. */
export function HotspotDetail({
  hotspot,
  onClose,
}: {
  hotspot: PublicHotspot;
  onClose: () => void;
}) {
  const isVideo = hotspot.type === 'video' && hotspot.video;

  if (isVideo && hotspot.video) {
    return (
      <div
        className="fixed inset-0 z-50 grid place-items-center bg-ink-900/90 p-6 backdrop-blur-sm"
        onClick={onClose}
      >
        <div
          className="w-full max-w-3xl border border-rule bg-ink-800"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between border-b border-rule px-4 py-3">
            <p className="font-mono text-[0.6rem] uppercase tracking-widest text-parchment-dim">
              {hotspot.title}
            </p>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="text-parchment-dim hover:text-parchment"
            >
              <Icon name="close" size={18} />
            </button>
          </div>
          <VideoPlayer asset={hotspot.video} autoPlay className="aspect-video w-full bg-black" />
          {hotspot.content && (
            <p className="px-4 py-3 text-sm leading-relaxed text-parchment-muted/80">
              {hotspot.content}
            </p>
          )}
        </div>
      </div>
    );
  }

  return (
    <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-sm flex-col border-l border-rule bg-ink-800/95 backdrop-blur-sm sv-chrome">
      <div className="flex items-center justify-between border-b border-rule px-5 py-4">
        <p className="label-eyebrow">{HOTSPOT_LABELS[hotspot.type]}</p>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="text-parchment-dim hover:text-parchment"
        >
          <Icon name="close" size={18} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-6">
        <h3 className="font-serif text-2xl leading-tight text-parchment">
          {hotspot.title}
        </h3>
        {hotspot.content && (
          <p className="editorial-prose mt-4 text-[0.95rem]">{hotspot.content}</p>
        )}

        {hotspot.type === 'audio' && hotspot.audio_track && (
          <audio
            className="mt-6 w-full"
            controls
            src={mediaUrl(hotspot.audio_track.file_path)}
          />
        )}

        {hotspot.type === 'external_link' && hotspot.target_url && (
          <a
            href={hotspot.target_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-6 inline-flex items-center gap-2 border border-accent px-4 py-2 font-mono text-[0.62rem] uppercase tracking-widest text-accent transition-colors hover:bg-accent hover:text-ink-900"
          >
            <Icon name="link" size={14} /> Open link
          </a>
        )}
      </div>
    </aside>
  );
}
