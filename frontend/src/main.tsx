import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Root container #root not found.');
}
const root = createRoot(container);

// The public surfaces (Graphic Novel Webviewer at /reader/*, Bookshop at /shop)
// are one code-split tree; everything else is the private admin app. They are
// mounted separately so the public bundle never includes the admin interface
// (and vice versa).
const publicPath = window.location.pathname;
if (publicPath.startsWith('/reader') || publicPath.startsWith('/shop')) {
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
