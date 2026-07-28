/// <reference types="vite/client" />

/** Env vars exposed to the browser. Without this TS doesn't know import.meta.env. */
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_GEMINI_API_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
