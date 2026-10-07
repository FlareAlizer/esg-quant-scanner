import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The dev server proxies /api to the Python backend, so the browser talks to
// one origin and the backend needs no CORS setup. Point BACKEND_URL elsewhere
// if uvicorn is not on its default port.
const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: { '/api': backend },
  },
});
