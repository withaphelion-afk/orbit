"""Context for every occurrence, so the ones that didn't fit can be read
individually instead of averaged away.

For each occurrence we record, as plain facts:
- the regime reading that day: the shared BTC/ETH gate for crypto, or the
  asset's own trend (same 50/200-day rule) for silver, with its scope;
- 20-day realised volatility as a percentile of the asset's own history;
- other transits that happened inside the same forward window, and which of
  those belong to a pattern whose own dominant outcome points the other way.

"Conflicting" depends on other patterns' results, so this runs as a second
pass after every pattern for the asset has been scored.
"""

from __future__ import annotations

import numpy as np

from orbit.core.types import ConfidenceLabel, Outcome, PatternResult, Regime, TransitEvent
from orbit.features.technical import technical_arrays
from orbit.analysis.confidence import RANK
from orbit.analysis.patterns import patterns_for_event
from orbit.analysis.series import PriceSeries
from orbit.analysis.transit_events import event_label

OPPOSITE = {
    Outcome.BIG_UP: {Outcome.BIG_DOWN, Outcome.SIDEWAYS},
    Outcome.BIG_DOWN: {Outcome.BIG_UP, Outcome.SIDEWAYS},
    Outcome.SIDEWAYS: {Outcome.BIG_UP, Outcome.BIG_DOWN},
}
REGIME_NAME = {1.0: Regime.BULL.value, -1.0: Regime.BEAR.value, 0.0: Regime.CHOPPY.value}


def volatility_percentiles(series: PriceSeries) -> np.ndarray:
    """Each bar's 20-day realised volatility as a 0-1 percentile of the whole history."""
    vol = technical_arrays(series.close)["volatility_20d"]
    out = np.full(len(vol), np.nan)
    ok = ~np.isnan(vol)
    ranks = vol[ok].argsort().argsort()
    out[ok] = ranks / max(1, ok.sum() - 1)
    return out


def regime_per_bar(series: PriceSeries, regime_by_day: dict) -> list[str | None]:
    return [REGIME_NAME.get(regime_by_day.get(d)) if d in regime_by_day else None for d in series.dates]


def annotate(
    results: dict[str, PatternResult],
    series: PriceSeries,
    event_bars: list[tuple[TransitEvent, int]],
    regimes: list[str | None],
    regime_scope: str,
    vol_pct: np.ndarray,
) -> None:
    """Fill regime / volatility / concurrency / exception fields on every occurrence, in place."""
    bars = np.array([b for _, b in event_bars])
    # For conflict checks: each event's most trustworthy pattern with a direction.
    def leaning(e: TransitEvent) -> tuple[Outcome, str] | None:
        best = None
        for pid in patterns_for_event(e):
            r = results.get(pid)
            if r is None or r.dominant_outcome is None or RANK[r.label] < RANK[ConfidenceLabel.WEAK]:
                continue
            if best is None or RANK[r.label] > RANK[best.label]:
                best = r
        return (best.dominant_outcome, best.pattern_id) if best else None

    for result in results.values():
        h = result.headline_horizon
        for occ in result.occurrences:
            i = _bar_of(series, occ.date)
            if i is None:
                continue
            occ.regime = regimes[i]
            occ.regime_scope = regime_scope if occ.regime else None
            occ.volatility_percentile = None if np.isnan(vol_pct[i]) else round(float(vol_pct[i]), 3)
            if h is None:
                continue
            window = np.flatnonzero((bars >= i) & (bars <= i + h))
            concurrent = [event_bars[j][0] for j in window if event_bars[j][0] != occ.event]
            occ.concurrent_events = [event_label(e) for e in concurrent]
            if result.dominant_outcome is not None:
                occ.is_exception = occ.outcome is not None and occ.outcome != result.dominant_outcome
                conflicts = []
                for e in concurrent:
                    lean = leaning(e)
                    if lean and lean[0] in OPPOSITE[result.dominant_outcome]:
                        conflicts.append(f"{event_label(e)} (leans {lean[0].value}, {lean[1]})")
                occ.conflicting_events = conflicts


def _bar_of(series: PriceSeries, date) -> int | None:
    d = np.datetime64(date.replace(tzinfo=None), "D")
    i = int(np.searchsorted(series.dates, d))
    if i >= len(series.dates) or (series.dates[i] - d).astype(int) > 3:
        return None
    return i
