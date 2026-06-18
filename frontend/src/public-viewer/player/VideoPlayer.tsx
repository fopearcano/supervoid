import { useState } from 'react';
import type { PublicMediaAsset } from '../types/reader';
import { mediaUrl } from '../api/publicClient';

/**
 * HTML5 video for intro / overlay / hotspot / ambient use.
 *
 * - `ambient` plays muted + looped + autoplay (the only safe autoplay form).
 * - non-ambient shows native controls; `autoPlay` is honoured only after the
 *   user has interacted (Enter overlay), so sound is allowed.
 * - Missing/blocked media falls back to the poster (or a quiet placeholder).
 */
export function VideoPlayer({
  asset,
  ambient = false,
  autoPlay = false,
  className = '',
}: {
  asset: PublicMediaAsset;
  ambient?: boolean;
  autoPlay?: boolean;
  className?: string;
}) {
  const [errored, setErrored] = useState(false);
  const url = mediaUrl(asset.file_path);
  const poster = mediaUrl(asset.poster_image);

  if (!url || errored) {
    return (
      <div
        className={`relative grid place-items-center overflow-hidden bg-ink-900 ${className}`}
      >
        {poster && (
          <img
            src={poster}
            alt=""
            className="absolute inset-0 h-full w-full object-cover opacity-40"
          />
        )}
        <span className="relative font-mono text-[0.6rem] uppercase tracking-widest text-parchment-shadow">
          Video unavailable
        </span>
      </div>
    );
  }

  return (
    <video
      key={asset.id}
      className={className}
      src={url}
      poster={poster}
      controls={!ambient}
      muted={ambient}
      autoPlay={ambient || autoPlay}
      loop={ambient || asset.loop}
      playsInline
      preload={ambient ? 'auto' : 'metadata'}
      onError={() => setErrored(true)}
    />
  );
}
