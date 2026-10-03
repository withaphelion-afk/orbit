import { createApi } from './http'
import { createStaticApi } from './static'

/**
 * The one API client the app uses: the live API server (a PC running Orbit), or,
 * in the free cloud build (VITE_ORBIT_STATIC=1), the snapshot in the private data repo.
 */
export const api =
  import.meta.env.VITE_ORBIT_STATIC === '1'
    ? createStaticApi({
        dataRepo: import.meta.env.VITE_ORBIT_DATA_REPO ?? '',
        codeRepo: import.meta.env.VITE_ORBIT_GITHUB_REPO ?? '',
      })
    : createApi(import.meta.env.VITE_ORBIT_API_BASE ?? '')
