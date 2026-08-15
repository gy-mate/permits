/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Origin the API is served from; empty when the frontend is proxied to it
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
