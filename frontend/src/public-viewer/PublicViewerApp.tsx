import { useEffect } from 'react';
import '../styles/supervoid-tokens.css';
import './styles/reader.css';
import { parseRoute, useLocation } from './router';
import { LandingPage } from './pages/LandingPage';
import { WorkDetailPage } from './pages/WorkDetailPage';
import { ReaderPage } from './pages/ReaderPage';

/**
 * Root of the public SUPERVOID Graphic Novel Webviewer. A standalone tree —
 * no admin shell, no auth context — mounted by main.tsx for /reader* paths.
 */
export function PublicViewerApp() {
  const pathname = useLocation();
  const route = parseRoute(pathname);

  useEffect(() => {
    document.title = 'SUPERVOID · Reader';
  }, []);

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
