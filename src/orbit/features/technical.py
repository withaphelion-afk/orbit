"""Turn raw candles into technical FeatureRecords: daily return, trend
position relative to the 50/200-day averages, and rolling volatility.

Features are stored as ratios/normalized values rather than raw prices,
since a feature store's whole point is letting different assets (BTC at
$80k, silver at $65) be compared and combined on the same scale.
"""

from __future__ import annotations

import statistics

from orbit.core.types import Candle, FeatureRecord

SHORT_WINDOW = 50
LONG_WINDOW = 200
VOLATILITY_WINDOW = 20


def compute_technical_features(candles: list[Candle]) -> list[FeatureRecord]:
    """One set of features per day, for every day that has enough history
    behind it (needs LONG_WINDOW prior candles for the 200-day average).
    """
    if len(candles) <= LONG_WINDOW:
        return []

    asset = candles[0].asset
    records = []

    for i in range(LONG_WINDOW, len(candles)):
        window = candles[i - LONG_WINDOW : i + 1]  # includes today, oldest-first
        today = window[-1]
        yesterday = window[-2]

        sma_short = sum(c.close for c in window[-SHORT_WINDOW:]) / SHORT_WINDOW
        sma_long = sum(c.close for c in window) / LONG_WINDOW
        daily_return = (today.close / yesterday.close) - 1

        vol_window = window[-VOLATILITY_WINDOW:]
        returns = [
            (vol_window[j].close / vol_window[j - 1].close) - 1
            for j in range(1, len(vol_window))
        ]
        volatility_20d = statistics.pstdev(returns)

        records.extend(
            [
                FeatureRecord(asset=asset, name="return_1d", date=today.timestamp, value=daily_return),
                FeatureRecord(
                    asset=asset,
                    name="close_vs_sma50",
                    date=today.timestamp,
                    value=(today.close / sma_short) - 1,
                ),
                FeatureRecord(
                    asset=asset,
                    name="close_vs_sma200",
                    date=today.timestamp,
                    value=(today.close / sma_long) - 1,
                ),
                FeatureRecord(asset=asset, name="volatility_20d", date=today.timestamp, value=volatility_20d),
            ]
        )
    return records
