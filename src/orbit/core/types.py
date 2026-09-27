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
