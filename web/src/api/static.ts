/**
 * The Orbit API, served as static files: the free cloud setup has no server.
 *
 * GitHub Actions jobs render every API answer to JSON (src/orbit/snapshot.py) and
 * publish it next to this app (deploy/hf-space/publish.py). This client reads
 * those files and gives the screens the same interface as the HTTP client, so
 * no screen knows the difference. What a static site can't do itself:
 * - live prices come straight from Binance's public market-data mirror (silver
 *   has no browser-readable live feed, so it shows the last stored close);
 * - Take/Skip/Modify and RUN ANALYSIS start GitHub workflows (decide.yml,
 *   analysis.yml) with a token you enter once, kept only in this browser. Their
 *   results appear with the next published snapshot, within a few minutes.
 */
import { ApiError, type OrbitApi } from './http'
import type {
  AnalysisRun,
  Asset,
  Candle,
  DecisionRequest,
  JournalRow,
  SuggestionView,
  SystemStatus,
  Tick,
  TransitView,
} from './types'

const TOKEN_KEY = 'orbit.githubToken'
const DECIDED_KEY = 'orbit.decided' // suggestion id -> when you decided, until the snapshot catches up
const RUN_KEY = 'orbit.startedRun'
const CATCH_UP_MS = 30 * 60_000
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

export function createStaticApi(base = './api', repo = '', fetcher: typeof fetch = (...a) => fetch(...a)): OrbitApi {
  const get = async <T>(file: string): Promise<T> => {
    let res: Response
    try {
      res = await fetcher(`${base}/${file}`, { cache: 'no-cache' })
    } catch {
      throw new ApiError(0, 'Could not load the published data. Check your connection and reload.')
    }
    if (res.status === 404) throw new ApiError(404, 'Not published yet. The next GitHub Actions run publishes it (hourly).')
    if (!res.ok) throw new ApiError(res.status, `${res.status} loading ${file}`)
    const body = await res.json()
    if (body && typeof body === 'object' && '__error' in body) throw new ApiError(body.__error.status, body.__error.detail)
    return body as T
  }

  const token = (): string => {
    const saved = load<string>(TOKEN_KEY, '')
    if (saved) return saved
    const entered = (
      window.prompt(
        `To act from this page, paste a GitHub fine-grained token for ${repo} with "Actions: Read and write". ` +
          'It is kept only in this browser.',
      ) ?? ''
    ).trim()
    if (!entered) throw new ApiError(401, 'No GitHub token entered, so nothing was sent.')
    save(TOKEN_KEY, entered)
    return entered
  }

  const dispatch = async (workflow: string, inputs: Record<string, string>): Promise<void> => {
    if (!repo) throw new ApiError(500, 'This build has no GitHub repo configured (VITE_ORBIT_GITHUB_REPO).')
    const res = await fetcher(`https://api.github.com/repos/${repo}/actions/workflows/${workflow}/dispatches`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token()}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' },
      body: JSON.stringify({ ref: 'main', inputs }),
    })
    if (res.status === 401 || res.status === 403 || res.status === 404) {
      save(TOKEN_KEY, '')
      throw new ApiError(res.status, 'GitHub refused the token (expired, or without "Actions: Read and write" on the repo). It was forgotten; try again to enter another.')
    }
    if (res.status !== 204) throw new ApiError(res.status, `GitHub answered ${res.status}: ${(await res.text()).slice(0, 200)}`)
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
    drift: () => get('drift.json'),
    backtest: () => get('backtest.json'),
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
