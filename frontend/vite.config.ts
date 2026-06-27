import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    // Bind to all interfaces (0.0.0.0 / ::) so the dev server is reachable from
    // other devices on the LAN, e.g. http://<your-lan-ip>:5173. The /api and
    // /public proxies still target the backend on the Vite host (127.0.0.1:8000).
    host: true,
    port: 5173,
    strictPort: false,
    proxy: {
      // Private admin API.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // Public Graphic Novel Webviewer API + its local demo media. The
      // frontend SPA owns /reader/*; /public/* belongs to the backend.
      '/public': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
