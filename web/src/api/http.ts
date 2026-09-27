/**
 * Talks to the Orbit backend over the contract in web/README.md.
 * Same-origin by default: in dev, Vite proxies /api and /ws to the backend.
 */
import type { Asset, DecisionRequest, OrbitSource, Tick } from './types'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on GET ${path}`)
  return res.json() as Promise<T>
}

export function createHttpSource(base = ''): OrbitSource {
  const url = (p: string) => base + p
  return {
    kind: 'http',
    quotes: () => get(url('/api/quotes')),
    candles: (a: Asset) => get(url(`/api/candles/${a}`)),
    signals: (a: Asset) => get(url(`/api/signals/${a}`)),
    suggestions: () => get(url('/api/suggestions')),
    async decide(id: string, req: DecisionRequest) {
      const res = await fetch(url(`/api/suggestions/${encodeURIComponent(id)}/decision`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(req),
      })
      if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
      return res.json()
    },
    journal: () => get(url('/api/journal')),
    drift: () => get(url('/api/drift')),
    astro: () => get(url('/api/astro')),
    system: () => get(url('/api/system')),
    subscribeTicks(onTick, onStatus) {
      let ws: WebSocket | undefined
      let retry: ReturnType<typeof setTimeout> | undefined
      let delay = 1000
      let closed = false
      const connect = () => {
        const wsBase = base ? base.replace(/^http/, 'ws') : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`
        ws = new WebSocket(`${wsBase}/ws`)
        ws.onopen = () => {
          delay = 1000
          onStatus?.(true)
        }
        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data)
            if (msg.type === 'tick') onTick(msg as Tick)
          } catch {
            // ignore malformed frames
          }
        }
        ws.onclose = () => {
          onStatus?.(false)
          if (closed) return
          retry = setTimeout(connect, delay)
          delay = Math.min(delay * 2, 30_000)
        }
      }
      connect()
      return () => {
        closed = true
        clearTimeout(retry)
        ws?.close()
      }
    },
  }
}
