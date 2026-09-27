"""Load stored prices as plain numpy arrays for the research.

Only *completed* daily bars are used: today's bar is still forming, and a
half-finished bar would quietly bias every forward return that touches it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from orbit.config.settings import TIMEFRAME
from orbit.core.types import Asset
from orbit.data.dates import today_utc
from orbit.data.storage import load_candles


def day64(d) -> np.datetime64:
    """A datetime (tz-aware or not) as numpy day precision."""
    return np.datetime64(d.replace(tzinfo=None), "D")


@dataclass
class PriceSeries:
    asset: Asset
    dates: np.ndarray  # datetime64[D], ascending
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray

    def __len__(self) -> int:
        return len(self.dates)


def hour64(d) -> np.datetime64:
    """A datetime as numpy hour precision (floored)."""
    return np.datetime64(d.replace(tzinfo=None), "h")


def load_price_series(asset: Asset, until=None, timeframe: str = TIMEFRAME) -> PriceSeries:
    """Completed bars only: for daily, bars before today; for hourly, before the current hour."""
    now = until or datetime.now(timezone.utc)
    if timeframe == "1h":
        cutoff, unit, stamp = hour64(now), "datetime64[h]", hour64
    else:
        cutoff, unit, stamp = day64(until or today_utc()), "datetime64[D]", day64
    candles = [c for c in load_candles(asset, timeframe) if stamp(c.timestamp) < cutoff]
    return PriceSeries(
        asset=asset,
        dates=np.array([stamp(c.timestamp) for c in candles], dtype=unit),
        open=np.array([c.open for c in candles], dtype=float),
        high=np.array([c.high for c in candles], dtype=float),
        low=np.array([c.low for c in candles], dtype=float),
        close=np.array([c.close for c in candles], dtype=float),
    )
