import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import fs from 'node:fs';
import { spawn, spawnSync, type ChildProcess } from 'node:child_process';

// vLLM runs on :8001 (`--host 127.0.0.1 --port 8001`); the SUPERVOID API keeps
// its conventional :8000 and the proxy points at it. A single `npm run dev`
// brings the whole local stack up against your local vLLM — no env files to
// edit. Override any value by exporting it before `npm run dev`
// (AI_MODEL / AI_API_KEY / VLLM_API_KEY / SUPERVOID_API_PORT), or set
// SUPERVOID_NO_BACKEND=1 to run the API yourself.
const BACKEND_DIR = path.resolve(__dirname, '../backend');
const API_PORT = Number(process.env.SUPERVOID_API_PORT ?? 8000);
const VLLM_BASE_URL = 'http://127.0.0.1:8001/v1';

function pythonBin(): string {
  const venv = path.join(BACKEND_DIR, '.venv', 'bin', 'python');
  return fs.existsSync(venv) ? venv : 'python3';
}

function backendEnv(): NodeJS.ProcessEnv {
  // Point the backend at the local vLLM without requiring a backend/.env.
  return {
    ...process.env,
    AI_PROVIDER: process.env.AI_PROVIDER ?? 'vllm',
    AI_BASE_URL: process.env.AI_BASE_URL ?? VLLM_BASE_URL,
    // Must match vLLM's --served-model-name (start vLLM with
    // `--served-model-name supervoid-brain`, or export AI_MODEL=<your name>).
    AI_MODEL: process.env.AI_MODEL ?? process.env.VLLM_SERVED_MODEL_NAME ?? 'supervoid-brain',
    AI_API_KEY: process.env.AI_API_KEY ?? process.env.VLLM_API_KEY ?? '',
  };
}

// Dev-only plugin: spawn (and clean up) the SUPERVOID API alongside Vite.
function supervoidBackend(): Plugin {
  let child: ChildProcess | undefined;
  return {
    name: 'supervoid-backend',
    apply: 'serve', // never runs during `vite build`
    configureServer(server) {
      if (process.env.SUPERVOID_NO_BACKEND) {
        server.config.logger.info('[supervoid] SUPERVOID_NO_BACKEND set — not starting the API.');
        return;
      }
      const py = pythonBin();
      const env = backendEnv();
      // Idempotent: seeds a usable demo DB on first run, prints "Seed skipped" after.
      try {
        spawnSync(py, ['-m', 'app.seed'], { cwd: BACKEND_DIR, env, stdio: 'inherit' });
      } catch {
        server.config.logger.warn('[supervoid] seed skipped (is the backend venv installed?)');
      }
      child = spawn(
        py,
        ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(API_PORT)],
        { cwd: BACKEND_DIR, env, stdio: 'inherit' },
      );
      child.on('exit', (code) => {
        if (code) server.config.logger.error(`[supervoid] API process exited (code ${code}).`);
      });
      const stop = () => {
        if (child && !child.killed) child.kill('SIGTERM');
        child = undefined;
      };
      server.httpServer?.once('close', stop);
      process.once('exit', stop);
      process.once('SIGINT', () => { stop(); process.exit(0); });
      process.once('SIGTERM', () => { stop(); process.exit(0); });
      server.config.logger.info(
        `[supervoid] API on http://127.0.0.1:${API_PORT} → vLLM ${env.AI_BASE_URL} (model ${env.AI_MODEL})`,
      );
    },
  };
}

const API_TARGET = `http://127.0.0.1:${API_PORT}`;

export default defineConfig({
  plugins: [react(), supervoidBackend()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    // Bind to all interfaces (0.0.0.0 / ::) so the dev server is reachable from
    // other devices on the LAN, e.g. http://<your-lan-ip>:5173. The /api and
    // /public proxies target the SUPERVOID API (NOT vLLM, which owns :8001).
    host: true,
    port: 5173,
    strictPort: false,
    proxy: {
      // Private admin API. The SPA talks to the backend ONLY through /api
      // (apiFetch prefixes it). Bare /brain and /mcp are NOT proxied here: the
      // OpenAI-compatible gateway (/brain/v1) and MCP (/mcp) are server-to-server
      // surfaces for LibreChat, and bare /brain/ is the production reverse-proxy
      // path to the LibreChat UI — never the FastAPI app.
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
      // Public Graphic Novel Webviewer API + its local demo media. The
      // frontend SPA owns /reader/*; /public/* belongs to the backend.
      '/public': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
});
