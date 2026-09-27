/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "http" to use the backend API; anything else uses the built-in mock. */
  readonly VITE_ORBIT_API?: string
  /** Optional absolute API origin, e.g. http://10.0.0.5:8000. Empty = same origin. */
  readonly VITE_ORBIT_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
