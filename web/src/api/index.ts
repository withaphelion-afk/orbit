import { createApi } from './http'

/** The one API client the app uses. Always the real backend; there is no mock. */
export const api = createApi(import.meta.env.VITE_ORBIT_API_BASE ?? '')
