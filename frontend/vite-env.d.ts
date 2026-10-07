/// <reference types="vite/client" />

/** Env vars exposed to the browser. Everything here ends up in the bundle. */
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
