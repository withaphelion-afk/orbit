"""Response shapes for the web API, mirroring web/src/api/types.ts field for
field. Keep these two files in sync by hand — the frontend's TS contract is
the source of truth for what the UI needs; this is Orbit's side of it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from orbit.core.types import Asset, Decision, Planet, Regime, Signal, TradeSuggestion

Source = Literal["LIVE", "MOCK"]


class Quote(BaseModel):
    asset: Asset
    last: float
    prev_close: float
    day_high: float
    day_low: float
    sparkline: list[float]
    regime: Regime
    source: Source


class SuggestionView(BaseModel):
    id: str
    created_at: datetime
    risk_reward: float
    suggestion: TradeSuggestion


class DecisionRequest(BaseModel):
    decision: Decision
    notes: str = ""
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None


class JournalRow(BaseModel):
    id: str
    decided_at: datetime
    entry: dict  # JournalEntry, kept loose since none exist yet
    counterfactual_pnl: float | None = None


class EquityPoint(BaseModel):
    time: datetime
    expected: float
    live: float
    band: float


class DriftReport(BaseModel):
    status: Literal["OK", "WATCH", "DRIFT"]
    z_score: float
    scale_down_at: float
    expected_win_rate: float
    live_win_rate: float
    expected_avg_r: float
    live_avg_r: float
    expected_max_dd: float
    live_max_dd: float
    backtest_trades: int
    live_trades: int
    curve: list[EquityPoint]


class AstroEvent(BaseModel):
    id: str
    timestamp: datetime
    body: Planet
    event: str
    prior_occurrences: int
    btc_5d_mean_after: float | None = None


class FeedStatus(BaseModel):
    asset: Asset
    source: Source
    last_bar: datetime


class AlertLog(BaseModel):
    timestamp: datetime
    level: Literal["INFO", "WARN", "ALERT"]
    message: str


class SystemStatus(BaseModel):
    runner: Literal["LIVE", "STALE", "DOWN"]
    strategy: str
    timeframe: str
    auto_execution: bool
    last_eval: datetime | None
    next_eval: datetime | None
    feeds: list[FeedStatus]
    alerts: list[AlertLog]
    config: dict[str, str]


class Tick(BaseModel):
    asset: Asset
    price: float
    timestamp: datetime


__all__ = [
    "Quote",
    "SuggestionView",
    "DecisionRequest",
    "JournalRow",
    "EquityPoint",
    "DriftReport",
    "AstroEvent",
    "FeedStatus",
    "AlertLog",
    "SystemStatus",
    "Tick",
    "Signal",
    "TradeSuggestion",
]
