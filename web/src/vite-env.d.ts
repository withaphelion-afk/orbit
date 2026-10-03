/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Optional absolute API origin, e.g. http://10.0.0.5:8000. Empty = same origin. */
  readonly VITE_ORBIT_API_BASE?: string
  /** "1" builds the static terminal that reads the published snapshot (free cloud hosting). */
  readonly VITE_ORBIT_STATIC?: string
  /** owner/name of the code repo whose workflows the static terminal starts. */
  readonly VITE_ORBIT_GITHUB_REPO?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
