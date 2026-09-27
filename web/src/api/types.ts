/**
 * The UI's vocabulary.
 *
 * The first block mirrors src/orbit/core/types.py field for field (snake_case,
 * ISO-8601 timestamps), so the JSON the backend emits drops straight in. The
 * second block is what the screens need on top of the core types — ids to act
 * on, derived numbers, status views. That block is the API contract the
 * backend is asked to serve; see web/README.md.
 */

// ---------- mirrors core/types.py ----------

export type Asset = 'BTC' | 'ETH' | 'SOL' | 'SILVER'
export type Direction = 'LONG' | 'SHORT'
export type Decision = 'TAKEN' | 'SKIPPED' | 'MODIFIED'
export type ISODateTime = string

export interface Candle {
  asset: Asset
  timestamp: ISODateTime
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface Signal {
  name: string
  asset: Asset
  timestamp: ISODateTime
  direction: Direction
  strength: number // 0.0 - 1.0
  reason: string
}

export interface TradeSuggestion {
  asset: Asset
  timestamp: ISODateTime
  direction: Direction
  confidence: number // 0.0 - 1.0
  entry_price: number
  stop_loss: number
  take_profit: number
  signals: Signal[]
}

export interface JournalEntry {
  suggestion: TradeSuggestion
  decision: Decision
  notes: string
  outcome_pnl: number | null // percent return on the position, e.g. 2.4 = +2.4%
}

// ---------- UI views (API contract) ----------

export type Source = 'LIVE' | 'MOCK'
export type Regime = 'TREND UP' | 'TREND DN' | 'RANGE'

export interface Quote {
  asset: Asset
  last: number
  prev_close: number
  day_high: number
  day_low: number
  sparkline: number[] // recent daily closes, oldest first
  regime: Regime
  source: Source
}

export interface SuggestionView {
  id: string
  created_at: ISODateTime
  risk_reward: number
  suggestion: TradeSuggestion
}

export interface DecisionRequest {
  decision: Decision
  notes: string
  // Only read for MODIFIED.
  entry_price?: number
  stop_loss?: number
  take_profit?: number
}

export interface JournalRow {
  id: string
  decided_at: ISODateTime
  entry: JournalEntry
  // What a SKIPPED suggestion would have returned, once that is knowable.
  counterfactual_pnl: number | null
}

export interface EquityPoint {
  time: ISODateTime
  expected: number // backtest-predicted equity, indexed to 100
  live: number // realised equity, indexed to 100
  band: number // 1-sigma half-width around expected
}

export interface DriftReport {
  status: 'OK' | 'WATCH' | 'DRIFT'
  z_score: number
  scale_down_at: number // |z| at which Orbit scales itself down
  expected_win_rate: number
  live_win_rate: number
  expected_avg_r: number
  live_avg_r: number
  expected_max_dd: number
  live_max_dd: number
  backtest_trades: number
  live_trades: number
  curve: EquityPoint[]
}

export interface AstroEvent {
  id: string
  timestamp: ISODateTime
  body: string
  event: string
  prior_occurrences: number
  btc_5d_mean_after: number | null // percent, null when not yet measured
}

export interface FeedStatus {
  asset: Asset
  source: Source
  last_bar: ISODateTime
}

export interface AlertLog {
  timestamp: ISODateTime
  level: 'INFO' | 'WARN' | 'ALERT'
  message: string
}

export interface SystemStatus {
  runner: 'LIVE' | 'STALE' | 'DOWN'
  strategy: string
  timeframe: string
  auto_execution: boolean
  last_eval: ISODateTime
  next_eval: ISODateTime
  feeds: FeedStatus[]
  alerts: AlertLog[]
  config: Record<string, string>
}

export interface Tick {
  asset: Asset
  price: number
  timestamp: ISODateTime
}

/** Everything the UI reads or writes. Mock and HTTP implementations are interchangeable. */
export interface OrbitSource {
  readonly kind: 'mock' | 'http'
  quotes(): Promise<Quote[]>
  candles(asset: Asset): Promise<Candle[]>
  signals(asset: Asset): Promise<Signal[]>
  suggestions(): Promise<SuggestionView[]>
  decide(id: string, req: DecisionRequest): Promise<JournalRow>
  journal(): Promise<JournalRow[]>
  drift(): Promise<DriftReport>
  astro(): Promise<AstroEvent[]>
  system(): Promise<SystemStatus>
  /** Streams live prices. Returns an unsubscribe function. */
  subscribeTicks(onTick: (tick: Tick) => void, onStatus?: (connected: boolean) => void): () => void
}
