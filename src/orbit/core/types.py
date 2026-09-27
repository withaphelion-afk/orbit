"""Shared data shapes used across every module in Orbit.

Keeping one definition of each concept here means data/, features/, strategy/
and journal/ all speak the same language instead of inventing their own
dicts. If you need to add a field, add it here once.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class Asset(str, Enum):
    BTC = "BTC"
    ETH = "ETH"
    SOL = "SOL"
    SILVER = "SILVER"


class Candle(BaseModel):
    """One OHLCV bar for a given asset and timeframe."""

    asset: Asset
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    # Where this bar came from, e.g. "binance:BTCUSDT" or "bitstamp:btcusd".
    # Full histories are stitched from more than one venue (see data/history.py),
    # so every bar keeps its own provenance.
    source: str = ""


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class Regime(str, Enum):
    """The shared market environment, computed from BTC/ETH trend + volatility.

    Gates whether per-asset entries are even considered — see
    features/regime.py for how this is derived.
    """

    BULL = "BULL"
    BEAR = "BEAR"
    CHOPPY = "CHOPPY"  # no clear trend — regime gate blocks new entries


class Signal(BaseModel):
    """One piece of evidence produced by a feature (technical, regime, astro, ...)."""

    name: str
    asset: Asset
    timestamp: datetime
    direction: Direction
    strength: float  # 0.0 - 1.0, how strongly this signal supports its direction
    reason: str  # human-readable explanation, shown in alerts and the journal


class TradeSuggestion(BaseModel):
    """What the strategy proposes, before you decide whether to act on it."""

    asset: Asset
    timestamp: datetime
    direction: Direction
    confidence: float  # 0.0 - 1.0, combined confidence across all signals
    entry_price: float
    stop_loss: float
    take_profit: float
    signals: list[Signal]


class Decision(str, Enum):
    TAKEN = "TAKEN"
    SKIPPED = "SKIPPED"
    MODIFIED = "MODIFIED"


class Planet(str, Enum):
    SUN = "SUN"
    MOON = "MOON"
    MERCURY = "MERCURY"
    VENUS = "VENUS"
    MARS = "MARS"
    JUPITER = "JUPITER"
    SATURN = "SATURN"
    URANUS = "URANUS"
    NEPTUNE = "NEPTUNE"
    PLUTO = "PLUTO"


class EphemerisSnapshot(BaseModel):
    """Where one planet was, on one day, from Earth's point of view.

    `longitude` is ecliptic longitude in degrees (0-360), the standard
    astrological/astronomical coordinate for "which zodiac sign." `sign`
    is that same position translated into a zodiac sign name for
    readability. `retrograde` is True when the planet's apparent motion
    is backward from Earth's viewpoint, computed by comparing today's
    longitude to yesterday's.
    """

    planet: Planet
    date: datetime
    longitude: float
    sign: str
    retrograde: bool


class FeatureRecord(BaseModel):
    """One computed signal value, for one asset, on one day.

    This is what the feature store holds — the layer between raw data
    (data/) and strategy logic (strategy/). Every feature (technical,
    regime, astro) gets written in this same shape, keyed by
    (asset, name, date), so the strategy layer and any future ML model
    can read them all the same way without caring how each was computed.

    `value` is always a float so features can be combined/scored
    uniformly — categorical features (e.g. a zodiac sign) get encoded as
    0/1 flags (one FeatureRecord per category) rather than stored as text.
    """

    asset: Asset
    name: str
    date: datetime
    value: float


class JournalEntry(BaseModel):
    """A logged suggestion plus what you did with it and how it played out.

    This is the record the feedback loop reweights the strategy from later.
    """

    suggestion: TradeSuggestion
    decision: Decision
    notes: str = ""
    outcome_pnl: float | None = None  # filled in once the trade is closed


# ---------------------------------------------------------------------------
# Transit research (analysis/). Retrospective research output, not a live
# signal: how each asset has historically behaved around planetary transits,
# with the statistics needed to judge whether any of it beats chance.
# ---------------------------------------------------------------------------


class TransitEventType(str, Enum):
    INGRESS = "INGRESS"  # planet enters a new sign
    STATION_RETROGRADE = "STATION_RETROGRADE"  # first day of apparent backward motion
    STATION_DIRECT = "STATION_DIRECT"  # first day moving forward again


class SpeedClass(str, Enum):
    """Groups planets by how fast they move, which sets the forward horizons
    worth measuring: a Moon ingress lasts ~2.5 days, a Saturn ingress ~2.5 years.
    """

    LUNAR = "LUNAR"
    FAST = "FAST"  # Sun, Mercury, Venus, Mars
    SLOW = "SLOW"  # Jupiter outward


class TransitEvent(BaseModel):
    """One discrete transit: (planet, event_type, from_state, to_state, date).

    For an ingress the states are sign names; for a station they are
    "DIRECT" / "RETROGRADE". `backward` marks an ingress made while retrograde
    (slipping back into the previous sign); `reentry` marks the forward
    ingress that follows one, so first entries can be analysed on their own.
    """

    planet: Planet
    event_type: TransitEventType
    date: datetime
    from_state: str
    to_state: str
    backward: bool = False
    reentry: bool = False


class Outcome(str, Enum):
    BIG_UP = "BIG_UP"  # forward return in the asset's own top tail
    BIG_DOWN = "BIG_DOWN"  # forward return in the asset's own bottom tail
    SIDEWAYS = "SIDEWAYS"  # little net displacement despite a normal range
    NEUTRAL = "NEUTRAL"  # none of the above


class ConfidenceLabel(str, Enum):
    INSUFFICIENT_DATA = "insufficient_data"  # too few occurrences to judge, however clean it looks
    NONE = "none"  # enough data, no evidence of an effect
    WEAK = "weak"  # nominally significant, but does not survive multiple-testing correction
    MODERATE = "moderate"  # survives FDR at the looser threshold
    STRONG = "strong"  # survives FDR at the strict threshold, with a real sample and effect


class PatternHorizonStat(BaseModel):
    """How one pattern's occurrences behaved over one forward horizon."""

    horizon_days: int
    n: int
    big_up_rate: float
    big_down_rate: float
    sideways_rate: float
    mean_return: float
    median_return: float
    win_rate: float  # share of occurrences with a positive forward return
    # Unconditional rates for this asset and horizon, for comparison.
    base_big_up_rate: float
    base_big_down_rate: float
    base_sideways_rate: float
    # One-sided p-values from the circular-shift null, and FDR-adjusted q-values.
    p_big_up: float | None = None
    p_big_down: float | None = None
    p_sideways: float | None = None
    q_big_up: float | None = None
    q_big_down: float | None = None
    q_sideways: float | None = None
    # Secondary check against uniformly random dates (reported, not FDR-corrected).
    p_uniform_best: float | None = None


class PatternOccurrence(BaseModel):
    """One historical occurrence of a pattern, with what followed and its context."""

    date: datetime
    event: TransitEvent
    outcome: Outcome | None  # None while the horizon hasn't elapsed yet
    forward_return: float | None
    is_exception: bool = False  # did not match the pattern's dominant outcome
    regime: str | None = None  # BULL/BEAR/CHOPPY at the time, None if not computable
    regime_scope: str | None = None  # "SHARED" (BTC/ETH gate) or "OWN" (asset's own trend)
    volatility_percentile: float | None = None  # 20d realised vol vs the asset's own history, 0-1
    concurrent_events: list[str] = []  # other transits inside the same forward window
    conflicting_events: list[str] = []  # concurrent transits whose own dominant outcome is the opposite


class PatternResult(BaseModel):
    """Everything known about one (asset, transit pattern)."""

    pattern_id: str  # e.g. "MARS:INGRESS:Aries" or "MERCURY:STATION_RETROGRADE"
    description: str
    planet: Planet
    event_type: TransitEventType
    sign: str | None = None  # set for per-sign ingress patterns
    speed_class: SpeedClass
    family: str  # multiple-testing family this pattern was corrected within
    n_events: int
    horizons: list[PatternHorizonStat]
    headline_horizon: int | None = None
    dominant_outcome: Outcome | None = None
    label: ConfidenceLabel
    score: int  # 0-100 blend of sample size, effect size and corrected significance
    summary: str
    occurrences: list[PatternOccurrence] = []


class SidewaysStateResult(BaseModel):
    """How often a transit *state* (e.g. "Mercury retrograde") coincides with chop."""

    state_id: str  # e.g. "MERCURY:RETROGRADE" or "SATURN:IN:Pisces"
    description: str
    horizon_days: int
    days_in_state: int
    episodes: int  # distinct stretches of the state: the honest sample size
    sideways_rate_in_state: float
    base_sideways_rate: float
    p_value: float | None
    q_value: float | None
    label: ConfidenceLabel
    score: int


class AssetPlaybook(BaseModel):
    asset: Asset
    generated_at: datetime
    history_start: datetime
    history_end: datetime
    bars: int
    patterns: list[PatternResult]
    sideways: list[SidewaysStateResult]


class PlaybookRunMeta(BaseModel):
    """What one playbook run tested, so every result can be read in context."""

    generated_at: datetime
    parameters: dict[str, float | int | str | bool | list[int]]
    tests_by_family: dict[str, int]
    total_tests: int
    assets: dict[str, dict[str, str | int]]
