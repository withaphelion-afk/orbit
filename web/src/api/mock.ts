/**
 * Built-in sample data, shaped exactly like the API contract in ./types.
 *
 * Seeded so every load looks the same. Suggestions and journal outcomes are
 * derived from the generated candles (real SMA/RSI/ATR maths, stops actually
 * walked forward), so the screens stay internally consistent. Nothing here is
 * market data; the UI shows a MOCK DATA badge whenever this source is active.
 */
import { ASSETS } from '../config'
import { riskReward } from '../lib/decision'
import { atr, rsi, sma } from '../lib/indicators'
import type {
  AlertLog,
  Asset,
  AstroEvent,
  Candle,
  DecisionRequest,
  Direction,
  DriftReport,
  JournalRow,
  OrbitSource,
  Quote,
  Planet,
  Regime,
  Signal,
  SuggestionView,
  SystemStatus,
  Tick,
  TradeSuggestion,
} from './types'

const DAY = 86_400_000
const NBARS = 240

interface Bar {
  t: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

const SPEC: Record<Asset, { base: number; vol: number; vb: number; trend: number; phase: number }> = {
  BTC: { base: 64210.5, vol: 0.028, vb: 24_000, trend: 0.0024, phase: 0.4 },
  ETH: { base: 3105.2, vol: 0.034, vb: 340_000, trend: 0, phase: 2.1 },
  SOL: { base: 148.23, vol: 0.045, vb: 3_100_000, trend: 0.0042, phase: 4.0 },
  SILVER: { base: 31.442, vol: 0.014, vb: 58_000, trend: -0.0021, phase: 1.3 },
}

// [days from today, body, event, prior occurrences, BTC 5-day mean after (%)]
const ASTRO_SEED: [number, Planet, string, number, number | null][] = [
  [-58, 'MARS', 'Ingress Leo', 7, 0.4],
  [-34, 'MERCURY', 'Stations retrograde', 12, -1.1],
  [-19, 'SUN', 'Conjunct Mercury', 9, 0.2],
  [-11, 'MOON', 'New moon', 38, 0.6],
  [2, 'MERCURY', 'Stations direct', 11, 1.3],
  [9, 'VENUS', 'Opposes Saturn', 6, -0.8],
  [16, 'MOON', 'Full moon', 37, -0.3],
  [27, 'JUPITER', 'Trine Saturn', 4, null],
  [41, 'MARS', 'Squares Jupiter', 8, 0.1],
]

const NOTES = [
  'Clean pullback to the 20D, took full size.',
  'Skipped: macro print the next morning.',
  'Tightened stop under the swing low.',
  'Entry late by half a day; filled worse.',
  'Skipped, already at max correlated exposure.',
  'Textbook. Let it run to target.',
  'Stopped on a wick, then it went. Stops might be too tight.',
  'Moved target to prior high.',
  'Took half size, low conviction.',
  'Skipped: weekend liquidity.',
  '',
  'Regime felt late; honoured the rule anyway.',
]

function mulberry32(seed: number) {
  let a = seed
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const iso = (t: number) => new Date(t).toISOString()

export interface MockOptions {
  seed?: number
  now?: number
  tickMs?: number
}

export function createMockSource(opts: MockOptions = {}): OrbitSource {
  const rand = mulberry32(opts.seed ?? 20260927)
  const gauss = () => {
    let u = 0
    let v = 0
    while (!u) u = rand()
    while (!v) v = rand()
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)
  }
  const now = opts.now ?? Date.now()
  const d0 = new Date(now)
  const today = Date.UTC(d0.getUTCFullYear(), d0.getUTCMonth(), d0.getUTCDate())

  // ---- candles
  const bars = {} as Record<Asset, Bar[]>
  for (const a of ASSETS) {
    const s = SPEC[a]
    const out: Bar[] = []
    let p = 1
    for (let i = 0; i < NBARS; i++) {
      let mu = 0.0012 * Math.sin(i / 33 + s.phase)
      if (i > NBARS - 70) mu += s.trend
      const r = mu + s.vol * gauss()
      const open = p * (1 + gauss() * s.vol * 0.12)
      p *= 1 + r
      const close = p
      out.push({
        t: today - (NBARS - 1 - i) * DAY,
        open,
        close,
        high: Math.max(open, close) * (1 + Math.abs(gauss()) * s.vol * 0.42),
        low: Math.min(open, close) * (1 - Math.abs(gauss()) * s.vol * 0.42),
        volume: s.vb * (0.55 + rand() * 0.8) * (1 + (Math.abs(r) / s.vol) * 0.45),
      })
    }
    const k = s.base / out[out.length - 1].close
    for (const b of out) {
      b.open *= k
      b.high *= k
      b.low *= k
      b.close *= k
    }
    bars[a] = out
  }

  const ind = {} as Record<Asset, { s20: number[]; s50: number[]; rsi: number[]; atr: number[] }>
  for (const a of ASSETS) {
    const closes = bars[a].map((b) => b.close)
    ind[a] = { s20: sma(closes, 20), s50: sma(closes, 50), rsi: rsi(closes), atr: atr(bars[a]) }
  }

  const regimeOf = (a: Asset, i = NBARS - 1) => {
    const s50 = ind[a].s50
    const dist = (bars[a][i].close / s50[i] - 1) * 100
    const slope = (s50[i] / s50[i - 10] - 1) * 100
    const tag: Regime = dist > 1.5 && slope > 0.3 ? 'BULL' : dist < -1.5 && slope < -0.3 ? 'BEAR' : 'CHOPPY'
    return { tag, dist, slope }
  }

  const toCandle = (a: Asset, b: Bar): Candle => ({
    asset: a,
    timestamp: iso(b.t),
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
    volume: b.volume,
  })

  const signal = (a: Asset, t: number, name: string, direction: Direction, strength: number, reason: string): Signal => ({
    name,
    asset: a,
    timestamp: iso(t),
    direction,
    strength: Math.round(strength * 100) / 100,
    reason,
  })

  // ---- chart signals: MA crosses and RSI extremes
  const chartSignals = {} as Record<Asset, Signal[]>
  for (const a of ASSETS) {
    const { s20, s50, rsi: r } = ind[a]
    const out: Signal[] = []
    for (let i = 51; i < NBARS; i++) {
      const t = bars[a][i].t
      if (s20[i - 1] < s50[i - 1] && s20[i] >= s50[i]) out.push(signal(a, t, 'ma_cross', 'LONG', 0.6, '20D average crossed above the 50D.'))
      if (s20[i - 1] > s50[i - 1] && s20[i] <= s50[i]) out.push(signal(a, t, 'ma_cross', 'SHORT', 0.6, '20D average crossed below the 50D.'))
      if (r[i - 1] >= 30 && r[i] < 30) out.push(signal(a, t, 'rsi_extreme', 'LONG', 0.5, `RSI(14) fell to ${r[i].toFixed(1)}.`))
      if (r[i - 1] <= 70 && r[i] > 70) out.push(signal(a, t, 'rsi_extreme', 'SHORT', 0.5, `RSI(14) rose to ${r[i].toFixed(1)}.`))
    }
    chartSignals[a] = out
  }

  // ---- pending suggestions, built from the indicators
  const suggestion = (
    a: Asset,
    direction: Direction,
    astroReason: string | null,
    against: { name: string; strength: number; reason: string } | null,
    targetAtr: number,
    ageMin: number,
  ): SuggestionView => {
    const n = NBARS - 1
    const b = bars[a]
    const t = b[n].t
    const rg = regimeOf(a)
    const last = b[n].close
    const a14 = ind[a].atr[n]
    const vol5 = b.slice(-5).reduce((s, x) => s + x.volume, 0) / 5
    const vol20 = b.slice(-20).reduce((s, x) => s + x.volume, 0) / 20
    const r14 = ind[a].rsi[n]
    const weighted: [Signal, number][] = [
      [
        signal(a, t, 'trend_regime', direction, Math.min(0.95, Math.max(0.35, Math.abs(rg.dist) / 7)),
          `Close ${Math.abs(rg.dist).toFixed(1)}% ${rg.dist > 0 ? 'above' : 'below'} the 50D average, which is ${rg.slope > 0 ? 'rising' : 'falling'} ${Math.abs(rg.slope).toFixed(1)}% over 10 days.`),
        0.4,
      ],
      [signal(a, t, 'rsi_14', direction, 0.45 + Math.min(0.4, Math.abs(r14 - 50) / 40), `RSI(14) at ${r14.toFixed(1)}. Momentum agrees with the trend without being stretched.`), 0.25],
      [signal(a, t, 'volume_confirm', direction, Math.min(0.9, Math.max(0.3, vol5 / vol20 - 0.4)), `5-day volume is ${(vol5 / vol20).toFixed(2)}× the 20-day average.`), 0.2],
    ]
    if (astroReason) weighted.push([signal(a, t, 'astro_transit', direction, 0.35, astroReason), 0.15])
    if (against) weighted.push([signal(a, t, against.name, direction === 'LONG' ? 'SHORT' : 'LONG', against.strength, against.reason), 0.2])
    let num = 0
    let den = 0
    for (const [s, w] of weighted) {
      num += w * s.strength * (s.direction === direction ? 1 : -1)
      den += w
    }
    const sd = direction === 'LONG' ? 1 : -1
    const sug: TradeSuggestion = {
      asset: a,
      timestamp: iso(now - ageMin * 60_000),
      direction,
      confidence: Math.round(Math.max(0.3, Math.min(0.92, 0.5 + (num / den) * 0.5)) * 100) / 100,
      entry_price: last,
      stop_loss: last - sd * 1.5 * a14,
      take_profit: last + sd * targetAtr * a14,
      signals: weighted.map(([s]) => s),
    }
    return {
      id: `${a}-${direction}-${t / DAY}`,
      created_at: sug.timestamp,
      risk_reward: riskReward(sug.entry_price, sug.stop_loss, sug.take_profit),
      suggestion: sug,
    }
  }

  const btcAtrPct = (ind.BTC.atr[NBARS - 1] / bars.BTC[NBARS - 1].close) * 100
  const pending: SuggestionView[] = [
    suggestion('SOL', 'LONG', 'Mercury stations direct in 2 days. Research weight is capped at 0.15.', null, 3.6, 134),
    suggestion('BTC', 'LONG', null, { name: 'volatility', strength: 0.42, reason: `ATR(14) is ${btcAtrPct.toFixed(1)}% of price, above its 60-day median. That argues for a smaller size.` }, 3.0, 47),
    suggestion('SILVER', 'SHORT', 'Venus opposes Saturn in 9 days. Research weight is capped at 0.15.', null, 2.8, 12),
  ]

  // ---- journal: past suggestions walked forward on the same candles
  const walk = (a: Asset, i: number, dir: Direction, stop: number, tp: number): number | null => {
    const b = bars[a]
    const sd = dir === 'LONG' ? 1 : -1
    const e = b[i].close
    for (let j = i + 1; j < Math.min(b.length, i + 21); j++) {
      if (sd > 0 ? b[j].low <= stop : b[j].high >= stop) return (stop / e - 1) * 100 * sd
      if (sd > 0 ? b[j].high >= tp : b[j].low <= tp) return (tp / e - 1) * 100 * sd
    }
    if (i + 20 > b.length - 1) return null
    return (b[i + 20].close / e - 1) * 100 * sd
  }
  const journal: JournalRow[] = []
  {
    const days = new Set<number>()
    while (days.size < 26) days.add(3 + Math.floor(rand() * 150))
    ;[...days]
      .sort((x, y) => y - x)
      .forEach((d, k) => {
        const a = ASSETS[Math.floor(rand() * 4)]
        const i = NBARS - 1 - d
        const b = bars[a][i]
        const s50 = ind[a].s50
        const direction: Direction = s50[i] > s50[i - 8] ? 'LONG' : 'SHORT'
        const sd = direction === 'LONG' ? 1 : -1
        const a14 = ind[a].atr[i]
        const stop = b.close - sd * 1.5 * a14
        const tp = b.close + sd * (2.6 + rand()) * a14
        const r = rand()
        const decision = r < 0.6 ? 'TAKEN' : r < 0.88 ? 'SKIPPED' : 'MODIFIED'
        const outcome = walk(a, i, direction, stop, tp)
        const rg = regimeOf(a, i)
        journal.push({
          id: `j${k}`,
          decided_at: iso(b.t + (8 + Math.floor(rand() * 10)) * 3_600_000),
          counterfactual_pnl: decision === 'SKIPPED' ? outcome : null,
          entry: {
            decision,
            notes: NOTES[Math.floor(rand() * NOTES.length)],
            outcome_pnl: decision === 'SKIPPED' ? null : outcome,
            suggestion: {
              asset: a,
              timestamp: iso(b.t),
              direction,
              confidence: Math.round((0.45 + rand() * 0.4) * 100) / 100,
              entry_price: b.close,
              stop_loss: stop,
              take_profit: tp,
              signals: [signal(a, b.t, 'trend_regime', direction, 0.6, `Regime ${rg.tag} at the time.`)],
            },
          },
        })
      })
  }

  // ---- drift
  const drift: DriftReport = (() => {
    const n = 90
    let live = 100
    const curve = []
    for (let t = 0; t < n; t++) {
      const expected = 100 * Math.exp(0.0011 * t)
      if (t) live *= 1 + 0.00035 + 0.0062 * gauss()
      curve.push({ time: iso(today - (n - 1 - t) * DAY), expected, live, band: expected * 0.0062 * Math.sqrt(t) })
    }
    const ew = 0.54
    const lw = 13 / 31
    const trades = 31
    const z = (lw - ew) / Math.sqrt((ew * (1 - ew)) / trades)
    return {
      status: Math.abs(z) >= 2 ? 'DRIFT' : Math.abs(z) >= 1 ? 'WATCH' : 'OK',
      z_score: z,
      scale_down_at: 2,
      expected_win_rate: ew,
      live_win_rate: lw,
      expected_avg_r: 0.38,
      live_avg_r: 0.19,
      expected_max_dd: -6.2,
      live_max_dd: -9.8,
      backtest_trades: 412,
      live_trades: trades,
      curve,
    }
  })()

  const astro: AstroEvent[] = ASTRO_SEED.map(([d, body, event, prior, after], k) => ({
    id: `ax${k}`,
    timestamp: iso(today + d * DAY),
    body,
    event,
    prior_occurrences: prior,
    btc_5d_mean_after: after,
  }))

  const alerts: AlertLog[] = [
    { timestamp: iso(now - 12 * 60_000), level: 'ALERT', message: 'New suggestion: XAG SHORT, confidence ' + pending[2].suggestion.confidence.toFixed(2) },
    { timestamp: iso(now - 47 * 60_000), level: 'ALERT', message: 'New suggestion: BTC LONG, confidence ' + pending[1].suggestion.confidence.toFixed(2) },
    { timestamp: iso(now - 95 * 60_000), level: 'WARN', message: 'Drift z-score crossed −1.0σ. Status is now WATCH.' },
    { timestamp: iso(now - 134 * 60_000), level: 'ALERT', message: 'New suggestion: SOL LONG, confidence ' + pending[0].suggestion.confidence.toFixed(2) },
    { timestamp: iso(now - 180 * 60_000), level: 'INFO', message: 'Daily evaluation complete: 4 assets, 3 suggestions' },
    { timestamp: iso(now - 181 * 60_000), level: 'INFO', message: 'Candles refreshed for BTC, ETH, SOL and SILVER' },
  ]

  // ---- live ticks: a small random walk applied to each asset's last bar
  const listeners = new Set<(t: Tick) => void>()
  let timer: ReturnType<typeof setInterval> | undefined
  const tickRand = mulberry32(7)
  const tick = () => {
    for (const a of ASSETS) {
      if (tickRand() < 0.35) continue
      const b = bars[a][NBARS - 1]
      const u = Math.max(1e-9, tickRand())
      const z = Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * tickRand())
      b.close *= 1 + z * SPEC[a].vol * 0.012
      b.high = Math.max(b.high, b.close)
      b.low = Math.min(b.low, b.close)
      const t: Tick = { asset: a, price: b.close, timestamp: iso(Date.now()) }
      listeners.forEach((fn) => fn(t))
    }
  }

  const clone = <T,>(v: T): T => structuredClone(v)

  return {
    kind: 'mock',
    async quotes(): Promise<Quote[]> {
      return ASSETS.map((a) => {
        const b = bars[a]
        const last = b[NBARS - 1]
        return {
          asset: a,
          last: last.close,
          prev_close: b[NBARS - 2].close,
          day_high: last.high,
          day_low: last.low,
          sparkline: b.slice(-30).map((x) => x.close),
          regime: regimeOf(a).tag,
          source: 'MOCK',
        }
      })
    },
    async candles(a) {
      return bars[a].map((b) => toCandle(a, b))
    },
    async signals(a) {
      return clone(chartSignals[a])
    },
    async suggestions() {
      return clone(pending)
    },
    async decide(id: string, req: DecisionRequest) {
      const k = pending.findIndex((p) => p.id === id)
      if (k < 0) throw new Error(`Suggestion ${id} is no longer pending`)
      const [view] = pending.splice(k, 1)
      const s = { ...view.suggestion }
      if (req.decision === 'MODIFIED') {
        s.entry_price = req.entry_price ?? s.entry_price
        s.stop_loss = req.stop_loss ?? s.stop_loss
        s.take_profit = req.take_profit ?? s.take_profit
      }
      const row: JournalRow = {
        id: `j-${Date.now()}`,
        decided_at: iso(Date.now()),
        counterfactual_pnl: null,
        entry: { suggestion: s, decision: req.decision, notes: req.notes, outcome_pnl: null },
      }
      journal.unshift(row)
      const label = s.asset === 'SILVER' ? 'XAG' : s.asset
      alerts.unshift({ timestamp: row.decided_at, level: 'INFO', message: `Decision logged: ${req.decision} ${label} ${s.direction}` })
      return clone(row)
    },
    async journal() {
      return clone(journal)
    },
    async drift() {
      return clone(drift)
    },
    async astro() {
      return clone(astro)
    },
    async system(): Promise<SystemStatus> {
      return {
        runner: 'LIVE',
        strategy: 'S1',
        timeframe: '1d',
        auto_execution: false,
        last_eval: iso(today),
        next_eval: iso(today + DAY),
        feeds: ASSETS.map((a) => ({ asset: a, source: 'MOCK', last_bar: iso(bars[a][NBARS - 1].t) })),
        alerts: clone(alerts),
        config: {
          TRACKED_ASSETS: ASSETS.join(' '),
          TIMEFRAME: '1d',
          TELEGRAM_BOT_TOKEN: 'not set',
          TELEGRAM_CHAT_ID: 'not set',
          DRIFT_SCALE_DOWN_AT: '2.0σ',
          ASTRO_WEIGHT_CAP: '0.15',
        },
      }
    },
    subscribeTicks(onTick, onStatus) {
      listeners.add(onTick)
      onStatus?.(true)
      if (!timer) timer = setInterval(tick, opts.tickMs ?? 1100)
      return () => {
        listeners.delete(onTick)
        if (!listeners.size && timer) {
          clearInterval(timer)
          timer = undefined
        }
      }
    },
  }
}
