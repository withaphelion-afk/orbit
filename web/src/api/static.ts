/**
 * The Orbit API without a server: the free cloud setup.
 *
 * GitHub Actions jobs render every API answer to JSON (src/orbit/snapshot.py) and
 * push it to the `site` branch of the private data repo (orbit.outputs --site).
 * This client reads those files through GitHub's API with your token, and gives
 * the screens the same interface as the HTTP client, so no screen knows the
 * difference. The app itself is public; without the token it shows nothing.
 * - Live prices come straight from Binance's public market-data mirror (silver
 *   has no browser-readable live feed, so it shows the last stored close).
 * - Take/Skip/Modify and RUN ANALYSIS start GitHub workflows (decide.yml,
 *   analysis.yml). Their results appear with the next snapshot, within minutes.
 * The token (fine-grained: Contents read on the data repo, Actions read/write on
 * the code repo) is asked for once and kept only in this browser.
 */
import { ApiError, type OrbitApi } from './http'
import type {
  AnalysisRun,
  Asset,
  Candle,
  DecisionRequest,
  DivergenceLabelRequest,
  JournalRow,
  ProjectionView,
  SuggestionView,
  SystemStatus,
  Tick,
  Timeframe,
  TransitView,
} from './types'

const TOKEN_KEY = 'orbit.githubToken'
const TOKEN_EVENT = 'orbit-token-changed'
// Tells the token screen; no-op where there is no window (tests).
const announce = () => typeof window !== 'undefined' && window.dispatchEvent(new Event(TOKEN_EVENT))

/** The saved GitHub token (static build only), and setting it from the app's token screen. */
export function hasToken(): boolean {
  return !!load<string>(TOKEN_KEY, '')
}
export function setToken(value: string): void {
  save(TOKEN_KEY, value.trim())
  announce()
}
export function onTokenChange(cb: () => void): () => void {
  window.addEventListener(TOKEN_EVENT, cb)
  return () => window.removeEventListener(TOKEN_EVENT, cb)
}
const DECIDED_KEY = 'orbit.decided' // suggestion id -> when you decided, until the snapshot catches up
const RUN_KEY = 'orbit.startedRun'
const CATCH_UP_MS = 30 * 60_000
const CACHE_MS = 60_000 // the snapshot changes hourly; screens poll far more often
const TICK_MS = 5_000
const BINANCE = 'https://data-api.binance.vision/api/v3/ticker/price'
const SYMBOLS: Partial<Record<Asset, string>> = { BTC: 'BTCUSDT', ETH: 'ETHUSDT', SOL: 'SOLUSDT' }

/** The file name of a pattern's snapshot: its id's UTF-8 bytes in hex (ids contain ':' and '|'). Same as snapshot.pattern_key. */
export function patternKey(id: string): string {
  return Array.from(new TextEncoder().encode(id), (b) => b.toString(16).padStart(2, '0')).join('')
}

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function save(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // private window or storage blocked: the action still went to GitHub
  }
}

const utcDay = (iso: string) => new Date(iso.slice(0, 10) + 'T00:00:00Z').getTime()

function newRunId(now = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0')
  const stamp = `${now.getUTCFullYear()}${p(now.getUTCMonth() + 1)}${p(now.getUTCDate())}-${p(now.getUTCHours())}${p(now.getUTCMinutes())}${p(now.getUTCSeconds())}`
  const hex = Array.from(crypto.getRandomValues(new Uint8Array(3)), (b) => b.toString(16).padStart(2, '0')).join('')
  return `${stamp}-${hex}`
}

export interface StaticSource {
  dataRepo: string // owner/name of the private repo whose `site` branch holds the snapshot
  codeRepo: string // owner/name of the repo whose workflows the actions start
  branch?: string
}

export function createStaticApi(source: StaticSource, fetcher: typeof fetch = (...a) => fetch(...a)): OrbitApi {
  const { dataRepo, codeRepo, branch = 'site' } = source

  // The app's own token screen (TokenGate) collects it: a browser pop-up is blocked on many phones and installed apps.
  const token = (): string => {
    const saved = load<string>(TOKEN_KEY, '')
    if (saved) return saved
    throw new ApiError(401, 'Not connected: enter a GitHub token to read your data.')
  }

  const refused = (status: number): ApiError => {
    save(TOKEN_KEY, '')
    announce() // brings the token screen back
    return new ApiError(status, 'GitHub refused the token (expired, or missing a permission). Enter another.')
  }

  const cache = new Map<string, { at: number; value: Promise<unknown> }>()
  const fetchFile = async (file: string): Promise<unknown> => {
    let res: Response
    try {
      res = await fetcher(`https://api.github.com/repos/${dataRepo}/contents/${file}?ref=${branch}`, {
        headers: { Authorization: `Bearer ${token()}`, Accept: 'application/vnd.github.raw+json', 'X-GitHub-Api-Version': '2022-11-28' },
      })
    } catch (e) {
      if (e instanceof ApiError) throw e
      throw new ApiError(0, 'Could not reach GitHub. Check your connection.')
    }
    if (res.status === 401 || res.status === 403) throw refused(res.status)
    if (res.status === 404) throw new ApiError(404, 'Not published yet. The next GitHub Actions run publishes it (hourly).')
    if (!res.ok) throw new ApiError(res.status, `${res.status} loading ${file}`)
    const body = await res.json()
    if (body && typeof body === 'object' && '__error' in body) throw new ApiError(body.__error.status, body.__error.detail)
    return body
  }
  const get = <T>(file: string): Promise<T> => {
    const hit = cache.get(file)
    if (hit && Date.now() - hit.at < CACHE_MS) return hit.value as Promise<T>
    const value = fetchFile(file)
    cache.set(file, { at: Date.now(), value })
    value.catch(() => cache.delete(file)) // never cache a failure
    return value as Promise<T>
  }

  const dispatch = async (workflow: string, inputs: Record<string, string>): Promise<void> => {
    const res = await fetcher(`https://api.github.com/repos/${codeRepo}/actions/workflows/${workflow}/dispatches`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token()}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' },
      body: JSON.stringify({ ref: 'main', inputs }),
    })
    if (res.status === 401 || res.status === 403 || res.status === 404) throw refused(res.status)
    if (res.status !== 204) throw new ApiError(res.status, `GitHub answered ${res.status}: ${(await res.text()).slice(0, 200)}`)
    cache.clear() // so the screens pick up the result as soon as it's published
  }

  /** Your recent decisions the published snapshot doesn't show yet. */
  const decided = (): Record<string, number> => {
    const now = Date.now()
    return Object.fromEntries(Object.entries(load<Record<string, number>>(DECIDED_KEY, {})).filter(([, at]) => now - at < CATCH_UP_MS))
  }

  return {
    quotes: () => get('quotes.json'),
    candles: (a: Asset) => get(`candles/${a}.json`),
    signals: (a: Asset) => get(`signals/${a}.json`),
    regime: () => get('regime.json'),
    async projections(days: number, includeNone: boolean) {
      // projections.json covers 60 days, weak and above; anything wider comes from projections-all.json (180 days, NONE included).
      const all = await get<ProjectionView[]>(days <= 60 && !includeNone ? 'projections.json' : 'projections-all.json')
      const until = Date.now() + days * 86_400_000
      return all.filter((p) => Date.parse(p.window_start) <= until && (includeNone || p.label !== 'none'))
    },
    projectionTrack: () => get('projections-track.json'),
    sky: () => get('sky.json'),
    async transits(from?: string, to?: string) {
      if (!from && !to) return get<TransitView[]>('transits.json')
      const all = await get<TransitView[]>('transits-all.json')
      const lo = from ? utcDay(from) : -Infinity
      const hi = to ? utcDay(to) : Infinity
      return all.filter((t) => {
        const d = new Date(t.event.date).getTime()
        return d >= lo && d <= hi
      })
    },
    playbookOverview: () => get('playbook.json'),
    playbook: (a: Asset) => get(`playbook/${a}.json`),
    pattern: (a: Asset, id: string) => get(`patterns/${a}/${patternKey(id)}.json`),
    async suggestions() {
      const done = decided()
      return (await get<SuggestionView[]>('suggestions.json')).filter((s) => !(s.id in done))
    },
    journal: () => get('journal.json'),
    drift: (tf: Timeframe = '1d') => get(tf === '1d' ? 'drift.json' : `drift-${tf}.json`),
    backtest: () => get('backtest.json'),
    bars: (a: Asset, tf: Timeframe) => get(`bars/${a}_${tf}.json`),
    divergences: (a: Asset) => get(`divergences/${a}.json`),
    divergenceModel: () => get('divergence-model.json'),
    alerts: () => get('alerts.json'),
    async labelDivergence(req: DivergenceLabelRequest): Promise<void> {
      // Saved by the label workflow in the private data repo; the next runner cycle trains on it.
      await dispatch('label.yml', {
        asset: req.asset,
        timeframe: req.timeframe,
        t1: String(req.t1),
        t2: String(req.t2),
        direction: req.direction,
        verdict: req.verdict,
        source: req.source ?? 'detected',
        note: req.note ?? '',
      })
    },
    calibration: () => get('calibration.json'),
    model: (a: Asset) => get(`model/${a}.json`),
    async system() {
      const s = await get<SystemStatus>('system.json')
      // The file says LIVE as of when it was published; past the runner's grace period it isn't any more.
      const last = s.runner.last_cycle_finished_at ?? s.runner.started_at
      const grace = (2 * (s.runner.interval_seconds ?? 3600) + 600) * 1000
      if (s.runner.state === 'LIVE' && last && Date.now() - new Date(last).getTime() > grace) s.runner.state = 'STALE'
      return s
    },
    runs: () => get('analysis/runs.json'),
    async currentRun() {
      const published = await get<AnalysisRun | null>('analysis/current.json')
      if (published) return published
      const mine = load<AnalysisRun | null>(RUN_KEY, null)
      if (!mine || Date.now() - new Date(mine.created_at).getTime() > CATCH_UP_MS) return null
      const runs = await get<AnalysisRun[]>('analysis/runs.json').catch(() => [] as AnalysisRun[])
      return runs.some((r) => r.id === mine.id && (r.status === 'succeeded' || r.status === 'failed')) ? null : mine
    },
    schedule: () => get('analysis/schedule.json'),
    async intraday(a: Asset, at: string, beforeHours: number, afterHours: number) {
      const t = new Date(at).getTime()
      const lo = t - beforeHours * 3_600_000
      const hi = t + afterHours * 3_600_000
      const years: number[] = []
      for (let y = new Date(lo).getUTCFullYear(); y <= new Date(hi).getUTCFullYear(); y++) years.push(y)
      const chunks = await Promise.all(
        years.map((y) => get<[string, number, number, number, number, number][]>(`hourly/${a}/${y}.json`).catch(() => [])),
      )
      return chunks
        .flat()
        .filter(([ts]) => {
          const ms = new Date(ts).getTime()
          return ms >= lo && ms <= hi
        })
        .map(([timestamp, open, high, low, close, volume]): Candle => ({ asset: a, timestamp, open, high, low, close, volume, source: '' }))
    },
    async startRun(opts: { placebo: boolean; refresh: boolean }): Promise<AnalysisRun> {
      const id = newRunId()
      await dispatch('analysis.yml', { placebo: String(opts.placebo), refresh: String(opts.refresh), run_id: id })
      const now = new Date().toISOString()
      const run: AnalysisRun = {
        id,
        trigger: 'manual',
        include_placebo: opts.placebo,
        refresh_data: opts.refresh,
        status: 'queued',
        created_at: now,
        started_at: null,
        finished_at: null,
        heartbeat_at: now,
        step: 'Started on GitHub Actions; results appear here when it finishes (about 20 minutes, 60 with the placebo check)',
        progress: 0,
        log: [],
        summary: {},
        changes: [],
        error: null,
      }
      save(RUN_KEY, run)
      return run
    },
    async decide(id: string, req: DecisionRequest): Promise<JournalRow> {
      await dispatch('decide.yml', {
        suggestion_id: id,
        decision: req.decision,
        notes: req.notes,
        entry_price: req.entry_price == null ? '' : String(req.entry_price),
        stop_loss: req.stop_loss == null ? '' : String(req.stop_loss),
        take_profit: req.take_profit == null ? '' : String(req.take_profit),
      })
      save(DECIDED_KEY, { ...decided(), [id]: Date.now() })
      // The journal row itself arrives with the next snapshot; the screens only refresh on this result.
      return { id, decided_at: new Date().toISOString(), expired: false, counterfactual_pnl: null, exit_reason: null } as unknown as JournalRow
    },

    /** Live crypto prices from Binance's public mirror, polled; silver has no browser-readable feed. */
    subscribeTicks(onTick: (t: Tick) => void, onStatus?: (connected: boolean) => void): () => void {
      let stopped = false
      const symbols = Object.entries(SYMBOLS) as [Asset, string][]
      const url = `${BINANCE}?symbols=${encodeURIComponent(JSON.stringify(symbols.map(([, s]) => s)))}`
      const poll = async () => {
        try {
          const res = await fetcher(url)
          if (!res.ok) throw new Error(String(res.status))
          const prices = (await res.json()) as { symbol: string; price: string }[]
          const now = new Date().toISOString()
          for (const [asset, symbol] of symbols) {
            const p = prices.find((x) => x.symbol === symbol)
            if (p) onTick({ asset, price: Number(p.price), timestamp: now, source: 'LIVE' })
          }
          onStatus?.(true)
        } catch {
          onStatus?.(false)
        }
      }
      void poll()
      const timer = setInterval(() => {
        if (!stopped) void poll()
      }, TICK_MS)
      return () => {
        stopped = true
        clearInterval(timer)
      }
    },
  }
}
