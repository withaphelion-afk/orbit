import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// When the Orbit API is running locally, the dev server proxies /api and /ws
// to it so the browser only ever talks to one origin. Point ORBIT_API_TARGET
// elsewhere if the backend runs on another port or machine.
const target = process.env.ORBIT_API_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  // The static cloud build is served from a Space's subpath-agnostic host: use relative asset URLs.
  base: process.env.VITE_ORBIT_STATIC === '1' ? './' : '/',
  plugins: [react()],
  server: {
    proxy: {
      '/api': target,
      '/ws': { target, ws: true },
    },
  },
})
