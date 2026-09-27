import { createHttpSource } from './http'
import { createMockSource } from './mock'
import type { OrbitSource } from './types'

/**
 * The one data source the app uses. VITE_ORBIT_API=http switches from the
 * built-in mock to the real backend; nothing else in the UI changes.
 */
export const source: OrbitSource =
  import.meta.env.VITE_ORBIT_API === 'http' ? createHttpSource(import.meta.env.VITE_ORBIT_API_BASE ?? '') : createMockSource()
