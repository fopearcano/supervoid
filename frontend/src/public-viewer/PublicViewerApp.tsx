import { useEffect } from 'react';
import '../styles/supervoid-tokens.css';
import './styles/reader.css';
import { parseRoute, useLocation } from './router';
import { LandingPage } from './pages/LandingPage';
import { ShopPage } from './pages/ShopPage';
import { WorkDetailPage } from './pages/WorkDetailPage';
import { ReaderPage } from './pages/ReaderPage';

/**
 * Root of the public SUPERVOID surfaces — the Graphic Novel Webviewer (/reader)
 * and the Bookshop (/shop). A standalone tree (no admin shell, no auth context)
 * mounted by main.tsx for /reader* and /shop paths.
 */
export function PublicViewerApp() {
  const pathname = useLocation();
  const route = parseRoute(pathname);

  useEffect(() => {
    document.title =
      route.name === 'shop' ? 'SUPERVOID · Bookshop' : 'SUPERVOID · Reader';
  }, [route.name]);

  if (route.name === 'shop') {
    return <ShopPage />;
  }
  if (route.name === 'work') {
    return <WorkDetailPage slug={route.slug} />;
  }
  if (route.name === 'reader') {
    return (
      <ReaderPage
        slug={route.slug}
        volumeId={route.volumeId}
        chapterId={route.chapterId}
      />
    );
  }
  return <LandingPage />;
}
