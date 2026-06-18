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
