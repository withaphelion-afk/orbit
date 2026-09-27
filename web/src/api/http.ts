/**
 * The Orbit API client. Same-origin by default: in dev, Vite proxies /api and
 * /ws to the backend (see vite.config.ts); VITE_ORBIT_API_BASE points it
 * elsewhere.
 */
import type {
  AnalysisRun,
  Asset,
  Candle,
  DecisionRequest,
  DriftReport,
  JournalRow,
  PatternResult,
  PlaybookOverview,
  PlaybookView,
  Quote,
  RegimeReading,
  ScheduleView,
  Signal,
  SkyPosition,
  SuggestionView,
  SystemStatus,
  Tick,
  TransitView,
} from './types'

/** An API error with the server's own explanation (FastAPI's `detail`). */
export class ApiError extends Error {
  readonly status: number
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
  }
}

async function parse<T>(res: Response, what: string): Promise<T> {
  if (res.ok) return res.json() as Promise<T>
  let detail = `${res.status} ${res.statusText} on ${what}`
  try {
    const body = await res.json()
    if (body && typeof body.detail === 'string') detail = body.detail
  } catch {
    // not JSON; keep the status line
  }
  throw new ApiError(res.status, detail)
}

export function createApi(base = '', fetcher: typeof fetch = (...a) => fetch(...a)) {
  const get = async <T>(path: string): Promise<T> => {
    let res: Response
    try {
      res = await fetcher(base + path, { headers: { Accept: 'application/json' } })
    } catch {
      throw new ApiError(0, 'The Orbit API is unreachable. Start it with: uv run python -m orbit.api')
    }
    return parse<T>(res, `GET ${path}`)
  }
  const enc = encodeURIComponent

  return {
    quotes: () => get<Quote[]>('/api/quotes'),
    candles: (a: Asset) => get<Candle[]>(`/api/candles/${a}`),
    signals: (a: Asset) => get<Signal[]>(`/api/signals/${a}`),
    regime: () => get<RegimeReading[]>('/api/regime'),
    sky: () => get<SkyPosition[]>('/api/sky'),
    transits: (from?: string, to?: string) => {
      const q = new URLSearchParams()
      if (from) q.set('from', from)
      if (to) q.set('to', to)
      const qs = q.toString()
      return get<TransitView[]>(`/api/transits${qs ? `?${qs}` : ''}`)
    },
    playbookOverview: () => get<PlaybookOverview>('/api/playbook'),
    playbook: (a: Asset) => get<PlaybookView>(`/api/playbook/${a}`),
    pattern: (a: Asset, id: string) => get<PatternResult>(`/api/playbook/${a}/patterns/${enc(id)}`),
    suggestions: () => get<SuggestionView[]>('/api/suggestions'),
    journal: () => get<JournalRow[]>('/api/journal'),
    drift: () => get<DriftReport>('/api/drift'),
    system: () => get<SystemStatus>('/api/system'),
    runs: () => get<AnalysisRun[]>('/api/analysis/runs'),
    currentRun: () => get<AnalysisRun | null>('/api/analysis/runs/current'),
    schedule: () => get<ScheduleView>('/api/analysis/schedule'),
    intraday: (a: Asset, at: string, beforeHours: number, afterHours: number) =>
      get<Candle[]>(`/api/intraday/${a}?at=${enc(at)}&before_hours=${beforeHours}&after_hours=${afterHours}`),
    async startRun(opts: { placebo: boolean; refresh: boolean }): Promise<AnalysisRun> {
      const res = await fetcher(`${base}/api/analysis/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(opts),
      })
      return parse<AnalysisRun>(res, 'POST run')
    },
    async decide(id: string, req: DecisionRequest): Promise<JournalRow> {
      const res = await fetcher(`${base}/api/suggestions/${enc(id)}/decision`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(req),
      })
      return parse<JournalRow>(res, 'POST decision')
    },

    /** Streams live prices. Reconnects with backoff. Returns an unsubscribe function. */
    subscribeTicks(onTick: (t: Tick) => void, onStatus?: (connected: boolean) => void): () => void {
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

export type OrbitApi = ReturnType<typeof createApi>
