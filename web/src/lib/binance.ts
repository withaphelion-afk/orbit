/**
 * Live crypto bars straight from Binance's public market-data mirror (no key, no geo-block):
 * the last 1,000 bars over REST, then the current bar over its WebSocket kline stream.
 * Silver isn't on Binance; its chart reads Orbit's own bars (hourly) instead.
 */
import type { Asset, BarRow, Timeframe } from '../api/types'

const REST = 'https://data-api.binance.vision/api/v3/klines'
const WS = 'wss://data-stream.binance.vision/ws'
export const BINANCE_SYMBOL: Partial<Record<Asset, string>> = { BTC: 'BTCUSDT', ETH: 'ETHUSDT', SOL: 'SOLUSDT' }

/** The last `limit` bars, the still-forming one included last. */
export async function fetchKlines(symbol: string, tf: Timeframe, limit = 1000): Promise<BarRow[]> {
  const res = await fetch(`${REST}?symbol=${symbol}&interval=${tf}&limit=${limit}`)
  if (!res.ok) throw new Error(`Binance answered ${res.status}`)
  const rows = (await res.json()) as [number, string, string, string, string, string][]
  return rows.map((k) => [Math.floor(k[0] / 1000), Number(k[1]), Number(k[2]), Number(k[3]), Number(k[4]), Number(k[5])])
}

/** Streams the current bar on every trade; `closed` is true on the update that finishes it. Returns an unsubscribe function. */
export function subscribeKlines(symbol: string, tf: Timeframe, onBar: (bar: BarRow, closed: boolean) => void): () => void {
  let ws: WebSocket | undefined
  let retry: ReturnType<typeof setTimeout> | undefined
  let stopped = false
  let delay = 1000
  const connect = () => {
    ws = new WebSocket(`${WS}/${symbol.toLowerCase()}@kline_${tf}`)
    ws.onopen = () => {
      delay = 1000
    }
    ws.onmessage = (e) => {
      try {
        const k = JSON.parse(e.data).k
        onBar([Math.floor(k.t / 1000), Number(k.o), Number(k.h), Number(k.l), Number(k.c), Number(k.v)], !!k.x)
      } catch {
        // ignore malformed frames
      }
    }
    ws.onclose = () => {
      if (stopped) return
      retry = setTimeout(connect, delay)
      delay = Math.min(delay * 2, 30_000)
    }
  }
  connect()
  return () => {
    stopped = true
    clearTimeout(retry)
    ws?.close()
  }
}
