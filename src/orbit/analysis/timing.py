"""Hourly drill-down: what happened around each transit's exact moment.

Two things, both on hourly bars:

1. The same question as the daily playbook, asked from the exact moment
   (to the hour) instead of the day: within 6 / 24 / 72 hours, was there a big
   up-move, a big down-move, or a sideways stretch, relative to the asset's own
   hourly history? Tested with the same circular shift (by at least 30 days)
   and corrected as its own family per asset.

2. Per occurrence, the shape of the move, measured from the exact moment:
   - hours_to_move: hours until price had moved one *daily* ATR in the
     move's direction (a normal day's range: "the move had clearly started");
   - hours_to_peak / peak_return: when the largest move in that direction
     within the window came, and how big it was;
   - pre_move_return: what price did in the 72 hours *before* the moment, to
     see whether a move was already under way.
   The direction is the pattern's dominant outcome (up or down); for sideways
   or neutral patterns it's the occurrence's own daily direction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from orbit.config.settings import TIMING_ATR_HOURS, TIMING_HORIZONS_HOURS
from orbit.core.types import TransitEvent
from orbit.analysis.outcomes import HorizonOutcomes, label_outcomes
from orbit.analysis.series import PriceSeries, hour64

PRE_HOURS = 72
MAX_GAP_HOURS = 72  # silver's weekend: an event on Saturday maps to Sunday night's first bar
MIN_HOURLY_BARS = 24 * 90


@dataclass
class HourlyContext:
    series: PriceSeries
    outcomes: dict[int, HorizonOutcomes]
    targets: dict[int, dict[int, np.ndarray]]


def build_context(series: PriceSeries, target_codes: tuple[int, ...]) -> HourlyContext | None:
    if len(series) < MIN_HOURLY_BARS:
        return None
    outcomes = {h: label_outcomes(series, h, atr_window=TIMING_ATR_HOURS) for h in TIMING_HORIZONS_HOURS}
    targets = {h: {t: (o.valid_codes == t).astype(float) for t in target_codes} for h, o in outcomes.items()}
    return HourlyContext(series, outcomes, targets)


def hour_index(series: PriceSeries, moment: datetime) -> int | None:
    """The bar containing `moment`, or the next bar if the market was closed then."""
    h = hour64(moment)
    i = int(np.searchsorted(series.dates, h, side="right")) - 1
    if i >= 0 and series.dates[i] == h:
        return i
    i += 1
    if i >= len(series.dates) or int((series.dates[i] - h).astype(int)) > MAX_GAP_HOURS:
        return None
    return i


def event_bars(ctx: HourlyContext, events: list[TransitEvent]) -> list[tuple[TransitEvent, int]]:
    out, seen = [], set()
    for e in events:
        if e.exact_time is None:
            continue
        i = hour_index(ctx.series, e.exact_time)
        if i is not None and i not in seen:
            seen.add(i)
            out.append((e, i))
    return out


def path_metrics(series: PriceSeries, i0: int, direction: int | None, window_hours: int, atr_fraction: float | None) -> dict:
    """Move timing from bar i0 (the bar holding the exact moment) over the window."""
    dates, high, low, close, open_ = series.dates, series.high, series.low, series.close, series.open
    p0 = float(open_[i0])
    start = dates[i0]
    pre_i = int(np.searchsorted(dates, start - np.timedelta64(PRE_HOURS, "h")))
    pre = float(p0 / close[pre_i] - 1) if pre_i < i0 else None
    end = int(np.searchsorted(dates, start + np.timedelta64(window_hours, "h")))
    out = {"hours_to_move": None, "hours_to_peak": None, "peak_return": None, "pre_move_return": pre}
    if direction is None or end <= i0:
        return out
    seg = slice(i0, end)
    excursion = (high[seg] / p0 - 1) if direction > 0 else (low[seg] / p0 - 1)
    k = int(np.argmax(excursion)) if direction > 0 else int(np.argmin(excursion))
    hours = (dates[seg] - start).astype(int)
    out["hours_to_peak"] = float(hours[k])
    out["peak_return"] = float(excursion[k])
    if atr_fraction:
        hit = np.flatnonzero(direction * excursion >= atr_fraction)
        if len(hit):
            out["hours_to_move"] = float(hours[hit[0]])
    return out
