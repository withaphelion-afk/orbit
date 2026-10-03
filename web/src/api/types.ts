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
/** The 9 Vedic grahas (Rahu and Ketu are the lunar nodes). URANUS..PLUTO exist in the backend enum but are never used. */
export type Planet = 'SUN' | 'MOON' | 'MERCURY' | 'VENUS' | 'MARS' | 'JUPITER' | 'SATURN' | 'RAHU' | 'KETU' | 'URANUS' | 'NEPTUNE' | 'PLUTO'
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

/** Vedic (Jyotish) events; see src/orbit/vedic/events.py. */
export type TransitEventType =
  | 'INGRESS'
  | 'NAKSHATRA_INGRESS'
  | 'STATION_RETROGRADE'
  | 'STATION_DIRECT'
  | 'YUTI'
  | 'DRISHTI'
  | 'COMBUSTION'
  | 'GRAHA_YUDDHA'
  | 'AMAVASYA'
  | 'PURNIMA'
  | 'SOLAR_ECLIPSE'
  | 'LUNAR_ECLIPSE'
  | 'YOGA'
  | 'CLUSTER'
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
  other_planet: Planet | null // the second graha, for yuti / drishti / yuddha
  retro_involved: boolean // a participating graha was vakri at the time
  label: string // e.g. "Shani (Saturn) enters Meena (Pisces)"
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
  rw_big_up?: number | null // Romano-Wolf (family-wise) p-values: a comparison column, not used for labels
  rw_big_down?: number | null
  rw_sideways?: number | null
  neighbour_support?: number | null // share of neighbouring horizons showing the same effect direction (diagnostic)
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

/** A graha's place in the sidereal (Vedic, Lahiri) zodiac right now. */
export interface SkyPosition {
  planet: Planet
  name: string // e.g. "Shani (Saturn)"
  longitude: number
  sign: string // rashi, e.g. "Meena (Pisces)"
  degree: number
  nakshatra: string
  pada: number // 1-4
  retrograde: boolean // vakri (always true for Rahu and Ketu)
  combust: boolean // asta
  dignity: string | null // uchcha / neecha
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

// ---------- strategy, journal, backtest ----------

export interface SuggestionView {
  id: string
  created_at: ISODateTime
  risk_reward: number
  suggestion: TradeSuggestion
  timeframe: Timeframe // the bars it lives on; expiry and outcome count bars of this timeframe
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
  decided_at: ISODateTime // when you decided, or when it expired undecided
  entry: JournalEntry
  expired: boolean // no decision in time (logged as SKIPPED)
  counterfactual_pnl: number | null // what a skipped/expired suggestion would have returned
  exit_reason: 'target' | 'stop' | 'time' | null
  timeframe: Timeframe
}

export interface EquityPoint {
  time: ISODateTime
  expected: number
  live: number
  band: number
}

export interface DriftReport {
  timeframe: Timeframe
  status: 'OK' | 'WATCH' | 'DRIFT'
  z_score: number
  scale_down_at: number
  min_trades: number // below this many live trades the status stays OK
  expected_win_rate: number
  live_win_rate: number
  expected_avg_r: number
  live_avg_r: number
  expected_max_dd: number // in R
  live_max_dd: number
  backtest_trades: number
  live_trades: number
  curve: EquityPoint[]
}

export interface BacktestStats {
  trades: number
  open?: number
  win_rate: number
  avg_r: number
  std_r: number
  avg_return_pct: number
  profit_factor: number | null
  total_r: number
  max_drawdown_r: number
  avg_bars_held: number
  exit_reasons: Record<'target' | 'stop' | 'time', number>
  by_direction: Record<Direction, { trades: number; win_rate: number | null; avg_r: number | null }>
  by_year: Record<string, { trades: number; wins: number; r: number }>
  equity_r?: { date: string; r: number }[]
}

/** GET /api/backtest (src/orbit/backtest/engine.py). */
export interface BacktestReport {
  generated_at: ISODateTime
  strategy: string
  parameters: Record<string, unknown>
  pooled: BacktestStats // 1D, also under timeframes
  assets: Record<string, BacktestStats>
  timeframes: Record<string, { pooled: BacktestStats; assets: Record<string, BacktestStats>; threshold: number }>
}

/** GET /api/calibration: the feedback loop, i.e. the learned divergence model (src/orbit/strategy/divergence_model.py). */
export interface CalibrationReport {
  trained_at: ISODateTime
  features: string[]
  n_backtest: number // divergences the market graded
  n_live: number // divergences you labelled
  thresholds?: Record<string, number>
  by_timeframe?: Record<string, { candidates: number; graded: number; worked: number | null }>
  agreement?: DivergenceAgreement
  base_win_rate: number | null
  skill: boolean // beat the plain win rate out-of-sample; only then does it set confidence
  note?: string
  weights?: { feature: string; weight: number }[]
  out_of_sample: {
    n: number
    brier: number
    brier_base_rate: number
    log_loss: number
    log_loss_base_rate: number
    auc: number | null
    buckets: { predicted: number; actual: number; n: number }[]
  } | null
}

export interface ModelScore {
  n: number
  log_loss: number
  climatology_log_loss: number
  skill: number // 1 - log loss / climatology log loss
  brier: number
  auc: number | null
}

/** GET /api/model/{asset}: does the Vedic sky add forecasting skill? (src/orbit/analysis/model.py) */
export interface ModelReport {
  asset: Asset
  generated_at: ISODateTime
  as_of: string
  method: string
  tech_features: string[]
  vedic_features: number
  retrain_years: number
  summary: string
  results: Record<
    string,
    {
      target: 'big_up' | 'big_down' | 'sideways'
      horizon_days: number
      base_rate: number
      scores: Record<string, ModelScore>
      vedic_log_loss_gain: number
      control_log_loss_gains: number[]
      years_vedic_better: number
      years: number
      verdict: 'adds skill' | 'no added skill' | 'unclear'
      top_vedic_features?: { state: string; description: string; weight: number }[]
    }
  >
  forecast: Record<string, { TECH: number; 'TECH+VEDIC': number; base_rate: number }>
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

// ---------- projections (analysis/projections.py, api/schemas.py) ----------

/** A pattern's past occurrences that happened in conditions like today's. */
export interface LikeNow {
  regime: string
  volatility_percentile: number
  n: number
  matches: number
  share: number
}

/** One upcoming event for one asset, with what history says followed it. Never a promise:
 * `trusted` is only true for patterns that survive multiple-testing correction. */
export interface Projection {
  id: string
  asset: Asset
  event: TransitEvent
  pattern_id: string
  description: string
  label: ConfidenceLabel
  score: number
  horizon_days: number
  outcome: Outcome
  n: number
  hit_rate: number
  base_rate: number
  lift: number | null
  ci_low: number
  ci_high: number
  q_value: number | null
  mean_return: number
  win_rate: number
  timing_headline_hours: number | null
  timing_dominant: Outcome | null
  timing_label: ConfidenceLabel
  median_hours_to_move: number | null
  window_start: ISODateTime
  window_end: ISODateTime
  like_now: LikeNow | null
  group_id: string
  conflict: boolean
  trusted: boolean
  note: string
}

export interface ProjectionView extends Projection {
  horizon_stat: PatternHorizonStat
}

export interface LoggedProjection {
  projection: Projection
  recorded_at: ISODateTime
  graded_at: ISODateTime | null
  graded_through: ISODateTime | null
  actual_outcome: Outcome | null
  forward_return: number | null
  hit: boolean | null
  void_reason: string | null
}

export interface TrackBucket {
  recorded: number
  pending: number
  graded: number
  void: number
  hits: number
  hit_rate: number | null
  avg_base_rate: number | null
}

export interface ProjectionTrack {
  first_recorded_at: ISODateTime | null
  total: TrackBucket
  by_label: Record<string, TrackBucket>
  recent: LoggedProjection[]
  note: string
}

// ---------- divergences (strategy/divergence.py, divergence_model.py) ----------

export type Timeframe = '1h' | '4h' | '1d' | '1w'

/** [time (epoch s), open, high, low, close, volume] */
export type BarRow = [number, number, number, number, number, number]

export interface DivergenceCandidate {
  id: string
  kind: 'regular' | 'hidden' | 'manual'
  direction: Direction
  forming: boolean
  t1: number // epoch seconds of each swing's bar
  t2: number
  confirmed_at: number | null
  p1: number
  p2: number
  r1: number
  r2: number
  score: number | null // the model's probability that it works
  oos_score: number | null
  alert: boolean
  outcome: 'worked' | 'failed' | null
  you: 'real' | 'not' | null
}

export interface DivergenceSet {
  generated_at: ISODateTime
  trusted: boolean
  thresholds: Record<string, number>
  candidates: Partial<Record<Timeframe, DivergenceCandidate[]>>
}

export interface DivergenceAgreement {
  labelled: number
  compared: number
  agree: number
  disagree: { id: string; you: string; market: string }[]
}

/** What the browser needs to score live divergences exactly as the backend does. */
export interface DivergenceModel {
  trained_at: ISODateTime
  features: string[]
  model: { mu: number[]; sd: number[]; coef: number[] } | null
  thresholds: Record<string, number>
  trusted: boolean
  base_rate: number | null
  agreement: DivergenceAgreement
  by_timeframe: Record<string, { candidates: number; graded: number; worked: number | null }>
}

export interface AlertItem extends DivergenceCandidate {
  asset: Asset
  timeframe: Timeframe
  trusted: boolean
}

export interface DivergenceLabelRequest {
  asset: Asset
  timeframe: Timeframe
  t1: number
  t2: number
  direction: Direction
  verdict: 'real' | 'not'
  note?: string
  source?: 'detected' | 'manual'
}
