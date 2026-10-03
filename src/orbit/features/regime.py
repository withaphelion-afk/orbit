"""The regime gate: a shared BTC/ETH-derived read on the market environment.

Idea: crypto assets are highly correlated, so instead of asking "is BTC
bullish, is ETH bullish, is SOL bullish" three separate times, we compute
one shared trend state from BTC and ETH (the market leaders) and use it to
gate whether per-asset entries are even considered at all. This stops the
system from taking a long on SOL while the broader market is actually
rolling over.

Trend logic (kept simple and readable on purpose):
- Compare the latest close to its 50-day and 200-day simple moving averages.
- BULL:  close > SMA50 > SMA200  (price above both averages, averages aligned up)
- BEAR:  close < SMA50 < SMA200  (mirror image, aligned down)
- Anything else (averages crossed, price whipsawing) -> CHOPPY

BTC and ETH must agree for a BULL or BEAR call; if they disagree, the
regime is CHOPPY, since that means the market lacks a clear shared trend.

Silver isn't correlated with crypto, so it has no shared gate. Where a
screen or the research needs a regime reading for silver, it uses silver's
own trend under the same rule (`compute_trend_series`), labelled as such.
"""

from __future__ import annotations

import numpy as np

from orbit.core.types import Asset, Candle, FeatureRecord, Regime
from orbit.features.arrays import rolling_mean

SHORT_WINDOW = 50
LONG_WINDOW = 200

_REGIME_VALUE = {Regime.BULL: 1.0, Regime.BEAR: -1.0, Regime.CHOPPY: 0.0}
VALUE_TO_REGIME = {v: k for k, v in _REGIME_VALUE.items()}


def trend_values(close: np.ndarray) -> np.ndarray:
    """Per-day trend as +1 (BULL) / -1 (BEAR) / 0 (CHOPPY); NaN before LONG_WINDOW bars exist."""
    close = np.asarray(close, dtype=float)
    s = rolling_mean(close, SHORT_WINDOW)
    l = rolling_mean(close, LONG_WINDOW)
    with np.errstate(invalid="ignore"):
        out = np.where((close > s) & (s > l), 1.0, np.where((close < s) & (s < l), -1.0, 0.0))
    out[np.isnan(l)] = np.nan
    return out


def regime_gate_by_day(btc_candles: list[Candle], eth_candles: list[Candle]) -> dict:
    """The shared gate per day ({date: +1/-1/0}): BTC and ETH trends must agree,
    else CHOPPY (0). Only defined on days where both have LONG_WINDOW of history."""
    btc = dict(zip((c.timestamp for c in btc_candles), trend_values([c.close for c in btc_candles])))
    eth = dict(zip((c.timestamp for c in eth_candles), trend_values([c.close for c in eth_candles])))
    gate = {}
    for day, b in btc.items():
        e = eth.get(day)
        if e is None or np.isnan(b) or np.isnan(e):
            continue
        gate[day] = b if b == e else 0.0
    return gate


def compute_regime_series(
    btc_candles: list[Candle], eth_candles: list[Candle], target_asset: Asset
) -> list[FeatureRecord]:
    """The regime gate's reading for every day with enough history behind
    it, as FeatureRecords for `target_asset` (BULL=1, BEAR=-1, CHOPPY=0).

    This lets the regime gate's own history be logged and later checked
    against how well it actually predicted moves, same as any other
    feature — not just used as a live, one-off reading.
    """
    if len(btc_candles) <= LONG_WINDOW or len(eth_candles) <= LONG_WINDOW:
        return []
    gate = regime_gate_by_day(btc_candles, eth_candles)
    return [FeatureRecord(asset=target_asset, name="regime", date=d, value=float(v)) for d, v in sorted(gate.items())]


def compute_trend_series(candles: list[Candle]) -> list[FeatureRecord]:
    """An asset's own trend under the gate's rule, as "trend" FeatureRecords."""
    if len(candles) <= LONG_WINDOW:
        return []
    asset = candles[0].asset
    trend = trend_values([c.close for c in candles])
    return [
        FeatureRecord(asset=asset, name="trend", date=c.timestamp, value=float(v))
        for c, v in zip(candles, trend)
        if not np.isnan(v)
    ]
