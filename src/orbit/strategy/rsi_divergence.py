"""The one active strategy: basic RSI(14) divergence on daily bars.

Bullish divergence: price makes a lower swing low while RSI(14) makes a
higher low, and the first low was in weak territory (RSI below
BULL_RSI_ZONE). Bearish is the mirror image: a higher swing high with a
lower RSI high, the first high above BEAR_RSI_ZONE.

A swing low (high) is a bar whose low (high) is the most extreme of the
PIVOT_LEFT bars before it and PIVOT_RIGHT bars after it. A swing can only be
known PIVOT_RIGHT bars later, so the signal fires on that confirmation bar,
using nothing that wasn't known then (no look-ahead).

Levels, set on the signal bar:
    entry   next bar's open (the backtest) / the signal bar's close (a live suggestion)
    stop    beyond the swing: its extreme -/+ STOP_ATR x ATR(14)
    target  TARGET_R x the risk from entry
    time    the trade closes after MAX_BARS bars if neither level is hit

Nothing here is fitted to the data: the parameters are the textbook ones,
chosen before looking at results.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from orbit.core.types import Direction
from orbit.features.arrays import rolling_mean, true_range, wilder_rsi
from orbit.analysis.series import PriceSeries

RSI_PERIOD = 14
PIVOT_LEFT = 5
PIVOT_RIGHT = 3
MIN_BARS_BETWEEN = 5
MAX_BARS_BETWEEN = 60
BULL_RSI_ZONE = 40.0
BEAR_RSI_ZONE = 60.0
STOP_ATR = 0.5
TARGET_R = 2.0
MAX_BARS = 30
NAME = "RSI(14) divergence"


@dataclass
class DivergenceSignal:
    direction: Direction
    signal_index: int  # the confirmation bar
    first_pivot: int
    second_pivot: int
    price_first: float
    price_second: float
    rsi_first: float
    rsi_second: float
    stop: float
    atr: float

    @property
    def rsi_difference(self) -> float:
        return abs(self.rsi_second - self.rsi_first)

    @property
    def price_change(self) -> float:
        return self.price_second / self.price_first - 1

    @property
    def bars_between(self) -> int:
        return self.second_pivot - self.first_pivot


def _pivots(values: np.ndarray, low: bool) -> np.ndarray:
    """Indices of swing lows (or highs): extreme of the PIVOT_LEFT bars before and PIVOT_RIGHT after."""
    n = len(values)
    out = []
    for i in range(PIVOT_LEFT, n - PIVOT_RIGHT):
        window = values[i - PIVOT_LEFT : i + PIVOT_RIGHT + 1]
        if (low and values[i] == window.min() and np.argmin(window) == PIVOT_LEFT) or (
            not low and values[i] == window.max() and np.argmax(window) == PIVOT_LEFT
        ):
            out.append(i)
    return np.array(out, dtype=int)


def find_signals(series: PriceSeries) -> list[DivergenceSignal]:
    """Every divergence in the history, each dated to its confirmation bar."""
    rsi = wilder_rsi(series.close, RSI_PERIOD)
    atr = rolling_mean(true_range(series.high, series.low, series.close), 14)
    signals: list[DivergenceSignal] = []
    for low in (True, False):
        prices = series.low if low else series.high
        piv = _pivots(prices, low)
        for k in range(1, len(piv)):
            j = piv[k]
            if np.isnan(rsi[j]) or np.isnan(atr[j + PIVOT_RIGHT]):
                continue
            # The most recent earlier pivot within range forms the pair.
            for i in reversed(piv[:k]):
                gap = j - i
                if gap < MIN_BARS_BETWEEN:
                    continue
                if gap > MAX_BARS_BETWEEN or np.isnan(rsi[i]):
                    break
                if low and prices[j] < prices[i] and rsi[j] > rsi[i] and rsi[i] < BULL_RSI_ZONE:
                    direction = Direction.LONG
                elif not low and prices[j] > prices[i] and rsi[j] < rsi[i] and rsi[i] > BEAR_RSI_ZONE:
                    direction = Direction.SHORT
                else:
                    break
                s = j + PIVOT_RIGHT
                a = float(atr[s])
                if direction == Direction.LONG:
                    stop = float(series.low[j : s + 1].min()) - STOP_ATR * a
                else:
                    stop = float(series.high[j : s + 1].max()) + STOP_ATR * a
                signals.append(DivergenceSignal(direction, int(s), int(i), int(j), float(prices[i]), float(prices[j]), float(rsi[i]), float(rsi[j]), stop, a))
                break
    return sorted(signals, key=lambda x: x.signal_index)


def levels(signal: DivergenceSignal, entry: float) -> tuple[float, float] | None:
    """(stop, target) for an entry price, or None if the entry is already past the stop."""
    risk = entry - signal.stop if signal.direction == Direction.LONG else signal.stop - entry
    if risk <= 0:
        return None
    target = entry + TARGET_R * risk if signal.direction == Direction.LONG else entry - TARGET_R * risk
    return signal.stop, target


def reason(signal: DivergenceSignal, series: PriceSeries) -> str:
    d1, d2 = str(series.dates[signal.first_pivot]), str(series.dates[signal.second_pivot])
    if signal.direction == Direction.LONG:
        return (
            f"Bullish RSI divergence: price made a lower low ({signal.price_first:,.4g} on {d1} -> {signal.price_second:,.4g} on {d2}) "
            f"while RSI(14) made a higher low ({signal.rsi_first:.1f} -> {signal.rsi_second:.1f}), {signal.bars_between} bars apart."
        )
    return (
        f"Bearish RSI divergence: price made a higher high ({signal.price_first:,.4g} on {d1} -> {signal.price_second:,.4g} on {d2}) "
        f"while RSI(14) made a lower high ({signal.rsi_first:.1f} -> {signal.rsi_second:.1f}), {signal.bars_between} bars apart."
    )
