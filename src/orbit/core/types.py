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


class JournalEntry(BaseModel):
    """A logged suggestion plus what you did with it and how it played out.

    This is the record the feedback loop reweights the strategy from later.
    """

    suggestion: TradeSuggestion
    decision: Decision
    notes: str = ""
    outcome_pnl: float | None = None  # filled in once the trade is closed
