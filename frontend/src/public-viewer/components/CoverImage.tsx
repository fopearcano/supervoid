import { useState } from 'react';
import { mediaUrl } from '../api/publicClient';

/**
 * A cover/illustration image that degrades to a quiet archival placeholder if
 * the asset is missing or fails to load — so the gallery never shows a broken
 * image icon.
 */
export function CoverImage({
  src,
  alt,
  className = '',
}: {
  src: string | null | undefined;
  alt: string;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const url = mediaUrl(src);

  if (!url || failed) {
    return (
      <div
        className={`grid h-full w-full place-items-center bg-gradient-to-b from-ink-650 to-ink-900 ${className}`}
        aria-label={alt}
      >
        <span className="px-4 text-center font-serif text-lg italic text-parchment-shadow">
          {alt}
        </span>
      </div>
    );
  }

  return (
    <img
      src={url}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
      className={`h-full w-full object-cover ${className}`}
    />
  );
}
