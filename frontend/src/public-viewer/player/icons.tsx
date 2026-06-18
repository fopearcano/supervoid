import type { ReactElement, SVGProps } from 'react';

export type IconName =
  | 'play'
  | 'pause'
  | 'mute'
  | 'sound'
  | 'prev'
  | 'next'
  | 'fullscreen'
  | 'exit-fullscreen'
  | 'zoom-in'
  | 'zoom-out'
  | 'fit-width'
  | 'fit-height'
  | 'single'
  | 'double'
  | 'scroll'
  | 'cinematic'
  | 'eye'
  | 'eye-off'
  | 'close'
  | 'link'
  | 'audio'
  | 'video'
  | 'info';

const PATHS: Record<IconName, ReactElement> = {
  play: <polygon points="6 4 20 12 6 20 6 4" fill="currentColor" stroke="none" />,
  pause: (
    <>
      <rect x="6" y="5" width="4" height="14" fill="currentColor" stroke="none" />
      <rect x="14" y="5" width="4" height="14" fill="currentColor" stroke="none" />
    </>
  ),
  sound: (
    <>
      <path d="M4 9v6h4l5 4V5L8 9H4z" />
      <path d="M16 8a5 5 0 0 1 0 8" />
    </>
  ),
  mute: (
    <>
      <path d="M4 9v6h4l5 4V5L8 9H4z" />
      <line x1="16" y1="9" x2="21" y2="15" />
      <line x1="21" y1="9" x2="16" y2="15" />
    </>
  ),
  prev: <polyline points="15 5 8 12 15 19" />,
  next: <polyline points="9 5 16 12 9 19" />,
  fullscreen: (
    <>
      <path d="M4 9V4h5" />
      <path d="M20 9V4h-5" />
      <path d="M4 15v5h5" />
      <path d="M20 15v5h-5" />
    </>
  ),
  'exit-fullscreen': (
    <>
      <path d="M9 4v5H4" />
      <path d="M15 4v5h5" />
      <path d="M9 20v-5H4" />
      <path d="M15 20v-5h5" />
    </>
  ),
  'zoom-in': (
    <>
      <circle cx="11" cy="11" r="7" />
      <line x1="21" y1="21" x2="16" y2="16" />
      <line x1="11" y1="8" x2="11" y2="14" />
      <line x1="8" y1="11" x2="14" y2="11" />
    </>
  ),
  'zoom-out': (
    <>
      <circle cx="11" cy="11" r="7" />
      <line x1="21" y1="21" x2="16" y2="16" />
      <line x1="8" y1="11" x2="14" y2="11" />
    </>
  ),
  'fit-width': (
    <>
      <line x1="3" y1="12" x2="21" y2="12" />
      <polyline points="6 9 3 12 6 15" />
      <polyline points="18 9 21 12 18 15" />
    </>
  ),
  'fit-height': (
    <>
      <line x1="12" y1="3" x2="12" y2="21" />
      <polyline points="9 6 12 3 15 6" />
      <polyline points="9 18 12 21 15 18" />
    </>
  ),
  single: <rect x="8" y="4" width="8" height="16" rx="1" />,
  double: (
    <>
      <rect x="3" y="4" width="8" height="16" rx="1" />
      <rect x="13" y="4" width="8" height="16" rx="1" />
    </>
  ),
  scroll: (
    <>
      <rect x="6" y="3" width="12" height="18" rx="1" />
      <polyline points="9 13 12 16 15 13" />
    </>
  ),
  cinematic: (
    <>
      <rect x="3" y="6" width="18" height="12" rx="1" />
      <line x1="3" y1="10" x2="21" y2="10" />
      <line x1="3" y1="14" x2="21" y2="14" />
    </>
  ),
  eye: (
    <>
      <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z" />
      <circle cx="12" cy="12" r="2.5" />
    </>
  ),
  'eye-off': (
    <>
      <path d="M9.9 5.1A9.8 9.8 0 0 1 12 5c6 0 10 7 10 7a17 17 0 0 1-3.2 3.8" />
      <path d="M6.2 6.2A17 17 0 0 0 2 12s4 7 10 7a9.8 9.8 0 0 0 3.9-.8" />
      <line x1="3" y1="3" x2="21" y2="21" />
    </>
  ),
  close: (
    <>
      <line x1="6" y1="6" x2="18" y2="18" />
      <line x1="18" y1="6" x2="6" y2="18" />
    </>
  ),
  link: (
    <>
      <path d="M14 4h6v6" />
      <line x1="20" y1="4" x2="11" y2="13" />
      <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
    </>
  ),
  audio: (
    <>
      <path d="M9 18V6l10-2v12" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="16" cy="16" r="3" />
    </>
  ),
  video: (
    <>
      <rect x="3" y="6" width="18" height="12" rx="2" />
      <polygon points="11 9 15 12 11 15 11 9" fill="currentColor" stroke="none" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <line x1="12" y1="11" x2="12" y2="16" />
      <circle cx="12" cy="8" r="0.6" fill="currentColor" />
    </>
  ),
};

export function Icon({
  name,
  size = 18,
  ...props
}: { name: IconName; size?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {PATHS[name]}
    </svg>
  );
}
