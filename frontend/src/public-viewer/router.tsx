// A deliberately tiny history-based router for the public reader. Avoids a
// new dependency and keeps the public viewer self-contained. Clean URLs:
//   /reader                                   -> landing
//   /reader/:slug                             -> work detail
//   /reader/:slug/:volumeId/:chapterId        -> reader

import { useCallback, useEffect, useState } from 'react';
import type { AnchorHTMLAttributes, MouseEvent, ReactNode } from 'react';

export type Route =
  | { name: 'landing' }
  | { name: 'work'; slug: string }
  | { name: 'reader'; slug: string; volumeId: string; chapterId: string };

export function parseRoute(pathname: string): Route {
  const seg = pathname.replace(/\/+$/, '').split('/').filter(Boolean);
  // seg[0] is always 'reader' (this app only mounts under /reader).
  if (seg.length <= 1) return { name: 'landing' };
  if (seg.length === 2) return { name: 'work', slug: decodeURIComponent(seg[1]) };
  return {
    name: 'reader',
    slug: decodeURIComponent(seg[1]),
    volumeId: seg[2],
    chapterId: seg[3],
  };
}

export function useLocation(): string {
  const [path, setPath] = useState(() => window.location.pathname);
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  return path;
}

export function navigate(to: string): void {
  if (to === window.location.pathname) return;
  window.history.pushState({}, '', to);
  window.dispatchEvent(new PopStateEvent('popstate'));
  window.scrollTo(0, 0);
}

type LinkProps = {
  to: string;
  children: ReactNode;
} & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'>;

export function Link({ to, children, onClick, ...rest }: LinkProps) {
  const handle = useCallback(
    (event: MouseEvent<HTMLAnchorElement>) => {
      onClick?.(event);
      if (event.defaultPrevented) return;
      if (
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey ||
        event.button !== 0
      ) {
        return;
      }
      event.preventDefault();
      navigate(to);
    },
    [to, onClick],
  );
  return (
    <a href={to} onClick={handle} {...rest}>
      {children}
    </a>
  );
}

// Route builders so callers never hand-concatenate paths.
export const readerPaths = {
  landing: () => '/reader',
  work: (slug: string) => `/reader/${encodeURIComponent(slug)}`,
  read: (slug: string, volumeId: string, chapterId: string) =>
    `/reader/${encodeURIComponent(slug)}/${volumeId}/${chapterId}`,
};
