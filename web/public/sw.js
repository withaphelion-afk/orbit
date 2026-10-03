// Orbit's service worker: makes the terminal installable and starts it fast.
// Only the app's own files are cached. Data (GitHub, the local API) and live
// prices (Binance) always go to the network, so nothing stale or private is kept.
const CACHE = 'orbit-shell-v1'

/** Store a copy of a good response (cloned before the page reads the body) and pass it on. */
function keep(req, res) {
  if (res.ok) {
    const copy = res.clone()
    caches.open(CACHE).then((c) => c.put(req, copy))
  }
  return res
}

self.addEventListener('install', () => self.skipWaiting())

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  const url = new URL(req.url)
  if (req.method !== 'GET' || url.origin !== self.location.origin || url.pathname.includes('/api/') || url.pathname.endsWith('/ws')) return

  // Hashed build files never change: cache first. The page itself: network first, cache when offline.
  if (url.pathname.includes('/assets/')) {
    event.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => keep(req, res)),
      ),
    )
    return
  }
  event.respondWith(
    fetch(req)
      .then((res) => keep(req, res))
      .catch(() => caches.match(req).then((hit) => hit || caches.match('./'))),
  )
})
