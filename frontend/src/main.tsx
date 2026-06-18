import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Root container #root not found.');
}
const root = createRoot(container);

// The public Graphic Novel Webviewer lives under /reader/*; everything else is
// the private admin app. They are mounted as separate, code-split trees so the
// public bundle never includes the admin interface (and vice versa).
if (window.location.pathname.startsWith('/reader')) {
  void import('./public-viewer/PublicViewerApp').then(({ PublicViewerApp }) => {
    root.render(
      <StrictMode>
        <PublicViewerApp />
      </StrictMode>,
    );
  });
} else {
  void import('./App').then(({ default: App }) => {
    root.render(
      <StrictMode>
        <App />
      </StrictMode>,
    );
  });
}
