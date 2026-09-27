/**
 * The UI's vocabulary, mirroring the backend field for field (snake_case,
 * ISO-8601 UTC timestamps):
 *
 * - the first block mirrors src/orbit/core/types.py
 * - the second mirrors src/orbit/api/schemas.py (what the API adds on top)
 *
 * Change a shape here only together with its Python original.
 */

// ---------- core/types.py ----------

export type Asset = 'BTC' | 'ETH' | 'SOL' | 'SILVER'
export type Direction = 'LONG' | 'SHORT'
/** Market environment from BTC/ETH trend. CHOPPY blocks new entries. */
export type Regime = 'BULL' | 'BEAR' | 'CHOPPY'
export type Planet = 'SUN' | 'MOON' | 'MERCURY' | 'VENUS' | 'MARS' | 'JUPITER' | 'SATURN' | 'URANUS' | 'NEPTUNE' | 'PLUTO'
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
  source: string // venue, e.g. "binance:BTCUSDT" or "bitstamp:btcusd"
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

export type TransitEventType = 'INGRESS' | 'STATION_RETROGRADE' | 'STATION_DIRECT'
export type SpeedClass = 'LUNAR' | 'FAST' | 'SLOW'
export type Outcome = 'BIG_UP' | 'BIG_DOWN' | 'SIDEWAYS' | 'NEUTRAL'
export type ConfidenceLabel = 'insufficient_data' | 'none' | 'weak' | 'moderate' | 'strong'

export interface TransitEvent {
  planet: Planet
  event_type: TransitEventType
  date: ISODateTime
  from_state: string
  to_state: string
  backward: boolean // ingress made while retrograde, back into the previous sign
  reentry: boolean // the forward ingress that follows a backward one
  exact_time: ISODateTime | null // the moment itself, to the second
}

export interface HorizonStatBase {
  n: number
  big_up_rate: number
  big_down_rate: number
  sideways_rate: number
  mean_return: number
  median_return: number
  win_rate: number
  base_big_up_rate: number
  base_big_down_rate: number
  base_sideways_rate: number
  p_big_up: number | null
  p_big_down: number | null
  p_sideways: number | null
  q_big_up: number | null
  q_big_down: number | null
  q_sideways: number | null
  p_uniform_best: number | null
}

/** Counted in daily bars from the day of the transit. */
export interface PatternHorizonStat extends HorizonStatBase {
  horizon_days: number
}

/** Counted in hourly bars from the transit's exact moment. */
export interface TimingHorizonStat extends HorizonStatBase {
  horizon_hours: number
}

export interface PatternOccurrence {
  date: ISODateTime
  event: TransitEvent
  outcome: Outcome | null
  forward_return: number | null
  is_exception: boolean
  regime: string | null
  regime_scope: string | null
  volatility_percentile: number | null
  concurrent_events: string[]
  conflicting_events: string[]
  hours_to_move: number | null // hours until price moved one daily ATR in the move's direction
  hours_to_peak: number | null
  peak_return: number | null
  pre_move_return: number | null // the 72 hours before the exact moment
}

interface PatternCore {
  pattern_id: string
  description: string
  planet: Planet
  event_type: TransitEventType
  sign: string | null
  speed_class: SpeedClass
  n_events: number
  horizons: PatternHorizonStat[]
  headline_horizon: number | null
  dominant_outcome: Outcome | null
  label: ConfidenceLabel
  score: number
  summary: string
  timing: TimingHorizonStat[]
  timing_headline_hours: number | null
  timing_dominant: Outcome | null
  timing_label: ConfidenceLabel
  timing_score: number
  timing_summary: string
  median_hours_to_move: number | null
}

export interface PatternResult extends PatternCore {
  family: string
  occurrences: PatternOccurrence[]
}

export interface SidewaysStateResult {
  state_id: string
  description: string
  horizon_days: number
  days_in_state: number
  episodes: number
  sideways_rate_in_state: number
  base_sideways_rate: number
  p_value: number | null
  q_value: number | null
  label: ConfidenceLabel
  score: number
}

// ---------- api/schemas.py ----------

export type PriceSource = 'LIVE' | 'DELAYED' | 'STORED'
export type RegimeScope = 'SHARED' | 'OWN'

export interface Quote {
  asset: Asset
  last: number
  prev_close: number
  day_high: number
  day_low: number
  sparkline: number[]
  regime: Regime | null
  regime_scope: RegimeScope
  source: PriceSource
  last_bar_date: ISODateTime
  updated_at: ISODateTime
}

export interface RegimeReading {
  scope: RegimeScope
  asset: Asset | null
  value: Regime | null
  since: ISODateTime | null
  history: [ISODateTime, Regime][]
}

export interface SkyPosition {
  planet: Planet
  longitude: number
  sign: string
  degree: number
  retrograde: boolean
  next_event: TransitEvent | null
}

export interface NotableFor {
  asset: Asset
  pattern_id: string
  label: ConfidenceLabel
  dominant_outcome: Outcome | null
}

export interface TransitView {
  event: TransitEvent
  label: string
  notable: NotableFor[]
}

export interface PatternSummary extends PatternCore {
  exceptions: number
}

export interface PlaybookView {
  asset: Asset
  generated_at: ISODateTime
  history_start: ISODateTime
  history_end: ISODateTime
  bars: number
  hourly_start: ISODateTime | null
  hourly_bars: number
  patterns: PatternSummary[]
  sideways: SidewaysStateResult[]
}

export interface PlaybookOverview {
  generated_at: ISODateTime
  total_tests: number
  tests_by_family: Record<string, number>
  runs_so_far: number
  parameters: Record<string, unknown>
  assets: Record<string, Record<string, string | number>>
  placebo: { checked_at: string; placebo_runs: number; runs_with_any_discovery: number; total_false_discoveries: number } | null
}

export interface RunnerStatus {
  state: 'LIVE' | 'STALE' | 'NEVER_RUN'
  started_at: ISODateTime | null
  interval_seconds: number | null
  cycles: number
  in_cycle: boolean
  last_cycle_finished_at: ISODateTime | null
  last_cycle_ok: boolean | null
  last_error: string | null
  next_cycle_at: ISODateTime | null
}

export interface Components {
  runner: boolean
  playbook: boolean
  strategy: boolean
  journal: boolean
  backtest: boolean
  alerts: boolean
}

export interface FeedStatus {
  asset: Asset
  sources: string[]
  first_bar: ISODateTime | null
  last_bar: ISODateTime | null
  bars: number
  live_source: PriceSource
  last_tick_at: ISODateTime | null
}

export interface LogLine {
  timestamp: ISODateTime
  level: string
  message: string
}

export interface SystemStatus {
  runner: RunnerStatus
  components: Components
  strategy: string | null
  timeframe: string
  auto_execution: boolean
  feeds: FeedStatus[]
  log: LogLine[]
  config: Record<string, string>
  playbook_generated_at: ISODateTime | null
}

export interface Tick {
  asset: Asset
  price: number
  timestamp: ISODateTime
  source: 'LIVE' | 'DELAYED'
}

// Contract for layers that aren't built yet (strategy, journal, backtest).
// The screens for them are ready and read /api/system's components first.

export interface SuggestionView {
  id: string
  created_at: ISODateTime
  risk_reward: number
  suggestion: TradeSuggestion
}

export interface DecisionRequest {
  decision: Decision
  notes: string
  entry_price?: number // only read for MODIFIED
  stop_loss?: number
  take_profit?: number
}

export interface JournalRow {
  id: string
  decided_at: ISODateTime
  entry: JournalEntry
  counterfactual_pnl: number | null // what a SKIPPED suggestion would have returned
}

export interface EquityPoint {
  time: ISODateTime
  expected: number
  live: number
  band: number
}

export interface DriftReport {
  status: 'OK' | 'WATCH' | 'DRIFT'
  z_score: number
  scale_down_at: number
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

// ---------- analysis runs (analysis/jobs.py) ----------

export type RunStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface LabelChange {
  asset: Asset
  pattern_id: string
  description: string
  kind: 'daily' | 'timing'
  before: ConfidenceLabel | null
  after: ConfidenceLabel
}

export interface AnalysisRun {
  id: string
  trigger: 'manual' | 'schedule'
  include_placebo: boolean
  refresh_data: boolean
  status: RunStatus
  created_at: ISODateTime
  started_at: ISODateTime | null
  finished_at: ISODateTime | null
  heartbeat_at: ISODateTime | null
  step: string
  progress: number
  log: string[]
  summary: {
    total_tests?: number
    tests_by_family?: Record<string, number>
    placebo?: { placebo_runs: number; runs_with_any_discovery: number; runs_with_any_timing_discovery: number }
  }
  changes: LabelChange[]
  error: string | null
}

export interface ScheduleView {
  enabled: boolean
  daily_at_utc: string
  placebo_weekday: number // 0 = Monday
  next_at: ISODateTime | null
  runner_running: boolean
  last_success_at: ISODateTime | null
  last_success_trigger: string | null
}
