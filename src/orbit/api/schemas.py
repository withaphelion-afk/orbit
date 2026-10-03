"""Response shapes the web terminal reads. They wrap the core types (never
redefine them) and add only what a screen needs: live prices, status views,
lighter list versions of the playbook.

web/src/api/types.ts mirrors this file; change both together.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from orbit.core.types import (
    Asset,
    ConfidenceLabel,
    Decision,
    JournalEntry,
    Outcome,
    PatternHorizonStat,
    Planet,
    Projection,
    SidewaysStateResult,
    SpeedClass,
    TimingHorizonStat,
    TradeSuggestion,
    TransitEvent,
    TransitEventType,
)

PriceSource = Literal["LIVE", "DELAYED", "STORED"]
RegimeScope = Literal["SHARED", "OWN"]


class Quote(BaseModel):
    asset: Asset
    last: float
    prev_close: float
    day_high: float
    day_low: float
    sparkline: list[float]  # last 30 daily closes, oldest first
    regime: str | None  # BULL / BEAR / CHOPPY
    regime_scope: RegimeScope  # SHARED = BTC/ETH gate, OWN = the asset's own trend
    source: PriceSource  # LIVE ticks, DELAYED (Yahoo futures), or STORED (last stored close)
    last_bar_date: datetime
    updated_at: datetime


class RegimeReading(BaseModel):
    scope: RegimeScope
    asset: Asset | None  # None for the shared gate
    value: str | None
    since: datetime | None  # first day of the current reading
    history: list[tuple[datetime, str]]  # every change, oldest first


class SkyPosition(BaseModel):
    """A graha's place in the sidereal (Vedic) zodiac right now."""

    planet: Planet
    name: str  # e.g. "Shani (Saturn)"
    longitude: float  # sidereal, 0-360
    sign: str  # rashi, e.g. "Meena (Pisces)"
    degree: float  # 0-30 within the rashi
    nakshatra: str
    pada: int  # 1-4
    retrograde: bool  # vakri (always true for Rahu and Ketu)
    combust: bool  # asta
    dignity: str | None  # uchcha / neecha
    next_event: TransitEvent | None  # next rashi change or station


class NotableFor(BaseModel):
    asset: Asset
    pattern_id: str
    label: ConfidenceLabel
    dominant_outcome: Outcome | None


class TransitView(BaseModel):
    event: TransitEvent
    label: str  # e.g. "MARS → Aries"
    notable: list[NotableFor]  # playbook patterns this event belongs to that rate weak or better


class PatternSummary(BaseModel):
    """A PatternResult without its occurrence list, for tables."""

    pattern_id: str
    description: str
    planet: Planet
    event_type: TransitEventType
    sign: str | None
    speed_class: SpeedClass
    n_events: int
    horizons: list[PatternHorizonStat]
    headline_horizon: int | None
    dominant_outcome: Outcome | None
    label: ConfidenceLabel
    score: int
    summary: str
    exceptions: int
    timing: list[TimingHorizonStat] = []
    timing_headline_hours: int | None = None
    timing_dominant: Outcome | None = None
    timing_label: ConfidenceLabel = ConfidenceLabel.INSUFFICIENT_DATA
    timing_score: int = 0
    timing_summary: str = ""
    median_hours_to_move: float | None = None


class PlaybookView(BaseModel):
    asset: Asset
    generated_at: datetime
    history_start: datetime
    history_end: datetime
    bars: int
    hourly_start: datetime | None = None
    hourly_bars: int = 0
    patterns: list[PatternSummary]
    sideways: list[SidewaysStateResult]


class PlaybookOverview(BaseModel):
    generated_at: datetime
    total_tests: int
    tests_by_family: dict[str, int]
    runs_so_far: int
    parameters: dict
    assets: dict[str, dict]
    placebo: dict | None  # latest scripts/placebo_check.py summary, if run


class RunnerStatus(BaseModel):
    state: Literal["LIVE", "STALE", "NEVER_RUN"]
    started_at: datetime | None = None
    interval_seconds: int | None = None
    cycles: int = 0
    in_cycle: bool = False
    last_cycle_finished_at: datetime | None = None
    last_cycle_ok: bool | None = None
    last_error: str | None = None
    next_cycle_at: datetime | None = None


class Components(BaseModel):
    """Which layers exist yet, so screens can say "not built" instead of pretending."""

    runner: bool
    playbook: bool
    strategy: bool
    journal: bool
    backtest: bool
    alerts: bool


class FeedStatus(BaseModel):
    asset: Asset
    sources: list[str]  # venues the stored history was stitched from
    first_bar: datetime | None
    last_bar: datetime | None
    bars: int
    live_source: PriceSource
    last_tick_at: datetime | None


class LogLine(BaseModel):
    timestamp: datetime
    level: str
    message: str


class SystemStatus(BaseModel):
    runner: RunnerStatus
    components: Components
    strategy: str | None
    timeframe: str
    auto_execution: bool
    feeds: list[FeedStatus]
    log: list[LogLine]  # newest first
    config: dict[str, str]
    playbook_generated_at: datetime | None


class SuggestionView(BaseModel):
    id: str
    created_at: datetime
    risk_reward: float
    suggestion: TradeSuggestion
    timeframe: str = "1d"  # 4h or 1d: the bars it lives on (expiry and outcome count bars of this timeframe)


class DivergenceLabelRequest(BaseModel):
    """✓ real / ✗ not real on a divergence, identified by its two swings' bar times (epoch seconds)."""

    asset: Asset
    timeframe: Literal["1h", "4h", "1d", "1w"]
    t1: int
    t2: int
    direction: Literal["LONG", "SHORT"]
    verdict: Literal["real", "not"]
    note: str = ""
    source: Literal["detected", "manual"] = "detected"  # manual: one detection missed, marked by clicking its two swings


class DecisionRequest(BaseModel):
    decision: Decision
    notes: str = ""
    entry_price: float | None = None  # only read for MODIFIED
    stop_loss: float | None = None
    take_profit: float | None = None


class JournalRow(BaseModel):
    id: str
    decided_at: datetime  # when you decided, or when it expired undecided
    entry: JournalEntry
    expired: bool = False  # no decision within SUGGESTION_EXPIRY_BARS (logged as SKIPPED)
    counterfactual_pnl: float | None  # what a skipped/expired suggestion would have returned
    exit_reason: str | None = None  # target / stop / time, once the outcome is known
    timeframe: str = "1d"


class EquityPoint(BaseModel):
    time: datetime
    expected: float
    live: float
    band: float


class DriftReport(BaseModel):
    status: Literal["OK", "WATCH", "DRIFT"]
    z_score: float
    scale_down_at: float
    min_trades: int  # below this many live trades the status stays OK
    expected_win_rate: float
    live_win_rate: float
    expected_avg_r: float
    live_avg_r: float
    expected_max_dd: float  # in R
    live_max_dd: float
    backtest_trades: int
    live_trades: int
    curve: list[EquityPoint]


class RunRequest(BaseModel):
    placebo: bool = False  # also run the placebo check (about 10x longer)
    refresh: bool = True  # fetch the latest prices and ephemeris first


class ScheduleView(BaseModel):
    enabled: bool
    daily_at_utc: str
    placebo_weekday: int  # 0 = Monday
    next_at: datetime | None  # as last reported by the runner
    runner_running: bool
    last_success_at: datetime | None
    last_success_trigger: str | None


class ProjectionView(Projection):
    """A projection plus the full stats of its headline horizon (n, every rate, p and q
    values), so the evidence panel can show the calculation. The pattern's full
    evidence, occurrences included, is /api/playbook/{asset}/patterns/{pattern_id}."""

    horizon_stat: PatternHorizonStat

