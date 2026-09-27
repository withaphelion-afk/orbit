"""Label what followed each day, per forward horizon, relative to the asset's
own history.

For a horizon of h bars starting at bar t:

- forward return  r = close[t+h] / close[t] - 1
- BIG_UP / BIG_DOWN: r in the asset's own top / bottom BIG_MOVE_PERCENTILE of
  all h-bar returns. Percentiles, not fixed %, because BTC and silver have
  completely different volatility.
- SIDEWAYS: the net move was small *for how much the market moved*:
  |close[t+h] - close[t]| / (ATR14[t] * sqrt(h)) is in the bottom
  SIDEWAYS_DISPLACEMENT_PERCENTILE, while the high-low range over the window
  (same normalisation) is at least SIDEWAYS_MIN_RANGE_PERCENTILE, so a dead,
  untraded stretch doesn't count as chop.
- NEUTRAL: anything else.

Big moves take precedence over SIDEWAYS. Days whose horizon hasn't elapsed,
or that lack 14 bars of ATR history, get no label.

Percentiles are computed over the whole history. That's fine for looking
back; anything the live strategy consumes later must use expanding-window
thresholds instead, or it would be using the future.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from orbit.config.settings import (
    BIG_MOVE_PERCENTILE,
    SIDEWAYS_DISPLACEMENT_PERCENTILE,
    SIDEWAYS_MIN_RANGE_PERCENTILE,
)
from orbit.core.types import Outcome
from orbit.features.arrays import rolling_mean, true_range
from orbit.analysis.series import PriceSeries

ATR_WINDOW = 14

# Integer codes used inside the vectorised maths.
NEUTRAL, BIG_UP, BIG_DOWN, SIDEWAYS, UNDEFINED = 0, 1, 2, 3, -1
CODE_TO_OUTCOME = {NEUTRAL: Outcome.NEUTRAL, BIG_UP: Outcome.BIG_UP, BIG_DOWN: Outcome.BIG_DOWN, SIDEWAYS: Outcome.SIDEWAYS}
OUTCOME_TO_CODE = {v: k for k, v in CODE_TO_OUTCOME.items()}


@dataclass
class HorizonOutcomes:
    horizon: int
    forward_return: np.ndarray  # per bar, NaN where undefined
    codes: np.ndarray  # per bar, UNDEFINED where undefined
    start: int  # first bar with a defined label
    end: int  # one past the last bar with a defined label
    thresholds: dict[str, float]

    @property
    def valid_codes(self) -> np.ndarray:
        return self.codes[self.start : self.end]

    def base_rate(self, code: int) -> float:
        v = self.valid_codes
        return float(np.mean(v == code)) if len(v) else float("nan")


def label_outcomes(series: PriceSeries, horizon: int, atr_window: int = ATR_WINDOW) -> HorizonOutcomes:
    n = len(series)
    close, high, low = series.close, series.high, series.low
    fwd = np.full(n, np.nan)
    disp = np.full(n, np.nan)
    rng = np.full(n, np.nan)
    atr = rolling_mean(true_range(high, low, close), atr_window)
    # Zero-range stretches (flat hours in quiet markets) give ATR 0; their ratios come out
    # inf/NaN and drop out of the labels below, so the divide warnings are just noise.
    with np.errstate(divide="ignore", invalid="ignore"):
        _fill(fwd, disp, rng, close, high, low, atr, n, horizon)

    defined = ~np.isnan(fwd) & ~np.isnan(disp)
    idx = np.flatnonzero(defined)
    codes = np.full(n, UNDEFINED, dtype=np.int8)
    if len(idx) == 0:
        return HorizonOutcomes(horizon, fwd, codes, 0, 0, {})

    f, d, r = fwd[defined], disp[defined], rng[defined]
    up = float(np.quantile(f, 1 - BIG_MOVE_PERCENTILE))
    down = float(np.quantile(f, BIG_MOVE_PERCENTILE))
    disp_max = float(np.quantile(d, SIDEWAYS_DISPLACEMENT_PERCENTILE))
    range_min = float(np.quantile(r, SIDEWAYS_MIN_RANGE_PERCENTILE))

    c = np.full(len(f), NEUTRAL, dtype=np.int8)
    c[(d <= disp_max) & (r >= range_min)] = SIDEWAYS
    c[f >= up] = BIG_UP
    c[f <= down] = BIG_DOWN
    codes[defined] = c
    # Defined bars are contiguous: from the first bar with ATR history to n - horizon.
    return HorizonOutcomes(
        horizon=horizon,
        forward_return=fwd,
        codes=codes,
        start=int(idx[0]),
        end=int(idx[-1]) + 1,
        thresholds={"big_up_return": up, "big_down_return": down, "sideways_max_displacement": disp_max, "sideways_min_range": range_min},
    )


def _fill(fwd, disp, rng, close, high, low, atr, n, horizon) -> None:
    """Forward return, ATR-normalised displacement and range for every bar with a full window."""
    if n <= horizon:
        return
    fwd[: n - horizon] = close[horizon:] / close[: n - horizon] - 1
    scale = atr[: n - horizon] * np.sqrt(horizon)
    disp[: n - horizon] = np.abs(close[horizon:] - close[: n - horizon]) / scale
    # High-low range over bars t+1 .. t+h.
    win_high = np.lib.stride_tricks.sliding_window_view(high[1:], horizon).max(axis=1)
    win_low = np.lib.stride_tricks.sliding_window_view(low[1:], horizon).min(axis=1)
    rng[: n - horizon] = (win_high[: n - horizon] - win_low[: n - horizon]) / scale


def bar_index_for(dates: np.ndarray, day: np.datetime64, max_gap_days: int = 3) -> int | None:
    """The bar an event on `day` belongs to: that day's bar, or the next one if the
    market was closed (silver on weekends). None if there's no bar close enough."""
    i = int(np.searchsorted(dates, day, side="left"))
    if i >= len(dates) or (dates[i] - day).astype(int) > max_gap_days:
        return None
    return i
