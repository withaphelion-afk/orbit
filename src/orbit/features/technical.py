"""Turn raw candles into technical FeatureRecords: daily return, trend
position relative to the 50/200-day averages, and rolling volatility.

Features are stored as ratios/normalized values rather than raw prices,
since a feature store's whole point is letting different assets (BTC at
$80k, silver at $65) be compared and combined on the same scale.

Computed as whole-array rolling windows (see features/arrays.py) rather than
per-day Python loops, so full multi-year histories stay fast.
"""

from __future__ import annotations

import numpy as np

from orbit.core.types import Candle, FeatureRecord
from orbit.features.arrays import pct_change, rolling_mean, rolling_std

SHORT_WINDOW = 50
LONG_WINDOW = 200
VOLATILITY_WINDOW = 20

FEATURE_NAMES = ("return_1d", "close_vs_sma50", "close_vs_sma200", "volatility_20d")


def technical_arrays(close: np.ndarray) -> dict[str, np.ndarray]:
    """Every technical feature for every day, NaN where history is too short."""
    returns = pct_change(close)
    return {
        "return_1d": returns,
        "close_vs_sma50": close / rolling_mean(close, SHORT_WINDOW) - 1,
        "close_vs_sma200": close / rolling_mean(close, LONG_WINDOW) - 1,
        # Population std of the daily returns inside a 20-bar window (19 of them),
        # matching the original per-day definition.
        "volatility_20d": rolling_std(returns, VOLATILITY_WINDOW - 1),
    }


def compute_technical_features(candles: list[Candle]) -> list[FeatureRecord]:
    """One set of features per day, for every day that has enough history
    behind it (needs LONG_WINDOW prior candles for the 200-day average).
    """
    if len(candles) <= LONG_WINDOW:
        return []

    asset = candles[0].asset
    arrays = technical_arrays(np.array([c.close for c in candles]))
    records = []
    for i in range(LONG_WINDOW, len(candles)):
        for name in FEATURE_NAMES:
            records.append(FeatureRecord(asset=asset, name=name, date=candles[i].timestamp, value=float(arrays[name][i])))
    return records
