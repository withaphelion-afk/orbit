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
"""

from __future__ import annotations

from orbit.core.types import Candle, Regime

SHORT_WINDOW = 50
LONG_WINDOW = 200


def simple_moving_average(candles: list[Candle], window: int) -> float:
    """Average close price over the last `window` candles."""
    if len(candles) < window:
        raise ValueError(f"need at least {window} candles, got {len(candles)}")
    closes = [c.close for c in candles[-window:]]
    return sum(closes) / window


def _trend_for(candles: list[Candle]) -> Regime:
    """Trend read for a single asset's candles, oldest-first."""
    sma_short = simple_moving_average(candles, SHORT_WINDOW)
    sma_long = simple_moving_average(candles, LONG_WINDOW)
    last_close = candles[-1].close

    if last_close > sma_short > sma_long:
        return Regime.BULL
    if last_close < sma_short < sma_long:
        return Regime.BEAR
    return Regime.CHOPPY


def compute_regime(btc_candles: list[Candle], eth_candles: list[Candle]) -> Regime:
    """The shared regime gate: BTC and ETH trend must agree, else CHOPPY."""
    btc_trend = _trend_for(btc_candles)
    eth_trend = _trend_for(eth_candles)

    if btc_trend == eth_trend:
        return btc_trend
    return Regime.CHOPPY
