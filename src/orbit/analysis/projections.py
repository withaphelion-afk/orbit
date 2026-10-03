"""Upcoming transits, each joined to the playbook's evidence for one asset.

A projection says only this: the event is coming, and in this asset's history
the pattern it belongs to was followed by OUTCOME in k of n cases within H
bars, against a base rate of B. Patterns that don't survive multiple-testing
correction are still listed (weak, or none on request) but carry
trusted=False and a note saying they are unproven, so no screen can pass them
off as a forecast. insufficient_data is never projected.

What was projected, and how it turned out, is kept in projection_log.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from orbit.core.types import (
    Asset,
    AssetPlaybook,
    ConfidenceLabel,
    LikeNow,
    Outcome,
    PatternHorizonStat,
    PatternResult,
    Projection,
    SpeedClass,
    TransitEvent,
)
from orbit.data.dates import utc_day
from orbit.analysis.confidence import RANK
from orbit.analysis.exceptions import volatility_percentiles
from orbit.analysis.patterns import patterns_for_event
from orbit.analysis.series import PriceSeries

DAYS_AHEAD = 60
LIKE_NOW_VOL_BAND = 0.2
WEEKDAYS_ONLY = {Asset.SILVER}  # no weekend bars; crypto trades every day
TRUSTED = {ConfidenceLabel.STRONG, ConfidenceLabel.MODERATE}
Z95 = 1.959963984540054
RATE = {Outcome.BIG_UP: "big_up", Outcome.BIG_DOWN: "big_down", Outcome.SIDEWAYS: "sideways"}
DESCRIBE = {Outcome.BIG_UP: "a big up-move", Outcome.BIG_DOWN: "a big down-move", Outcome.SIDEWAYS: "a sideways stretch"}


@dataclass
class Conditions:
    """An asset's state on its last completed bar, for "in conditions like now"."""

    regime: str | None
    volatility_percentile: float | None


def current_conditions(series: PriceSeries, regime: str | None) -> Conditions:
    vol = volatility_percentiles(series) if len(series) else np.array([])
    # Rounded like the occurrences' own values, so the +-band compares like with like.
    last = round(float(vol[-1]), 3) if len(vol) and not np.isnan(vol[-1]) else None
    return Conditions(regime, last)


def wilson_interval(rate: float, n: int, z: float = Z95) -> tuple[float, float]:
    """95% Wilson score interval for a proportion; honest at small n, unlike rate +- 2 se."""
    if n <= 0:
        return 0.0, 1.0
    z2 = z * z
    denom = 1 + z2 / n
    centre = (rate + z2 / (2 * n)) / denom
    half = z * math.sqrt(rate * (1 - rate) / n + z2 / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _utc(d: datetime) -> datetime:
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def event_moment(e: TransitEvent) -> datetime:
    return _utc(e.exact_time or e.date)


def trades_on(asset: Asset, day: datetime) -> bool:
    return asset not in WEEKDAYS_ONLY or day.weekday() < 5


def window_end(asset: Asset, day: datetime, horizon: int) -> datetime:
    """The day of the bar `horizon` bars after the event's own bar (the event day's,
    or the next trading day's when the market is closed, as bar_index_for does).
    Projected calendar: weekends skipped for silver, holidays not known in advance."""
    d = utc_day(day)
    while not trades_on(asset, d):
        d += timedelta(days=1)
    for _ in range(horizon):
        d += timedelta(days=1)
        while not trades_on(asset, d):
            d += timedelta(days=1)
    return d


def projection_id(asset: Asset, pattern_id: str, e: TransitEvent) -> str:
    # To the minute: a recomputed ephemeris can move an exact moment by a second,
    # which must not turn the same prediction into a new one in the log.
    when = f"{event_moment(e):%Y-%m-%dT%H:%MZ}" if e.exact_time else f"{utc_day(e.date):%Y-%m-%d}"
    return f"{asset.value}@{pattern_id}@{when}"


def headline_stat(r: PatternResult) -> PatternHorizonStat | None:
    return next((s for s in r.horizons if s.horizon_days == r.headline_horizon), None)


def like_now(r: PatternResult, outcome: Outcome, cond: Conditions | None) -> LikeNow | None:
    if r.speed_class == SpeedClass.LUNAR or cond is None or cond.regime is None or cond.volatility_percentile is None:
        return None
    pool = [
        o for o in r.occurrences
        if o.outcome is not None and o.regime == cond.regime and o.volatility_percentile is not None
        and abs(o.volatility_percentile - cond.volatility_percentile) <= LIKE_NOW_VOL_BAND + 1e-9
    ]
    if not pool:
        return None
    matches = sum(1 for o in pool if o.outcome == outcome)
    return LikeNow(regime=cond.regime, volatility_percentile=cond.volatility_percentile, n=len(pool), matches=matches,
                   share=matches / len(pool))


def _note(label: ConfidenceLabel, outcome: Outcome, n: int, rate: float, base: float, horizon: int, q: float | None) -> str:
    hits = round(rate * n)
    days = "trading day" if horizon == 1 else "trading days"
    body = f"{hits} of {n} past occurrences were followed by {DESCRIBE[outcome]} within {horizon} {days} ({rate:.0%} vs {base:.0%} normally"
    if label in TRUSTED:
        qs = f", q = {q:.3f}" if q is not None else ""
        return f"{label.value.capitalize()} evidence: {body}{qs}); a historical tendency, not a promise."
    if label == ConfidenceLabel.WEAK:
        return f"Unproven, not significant: {body}), which does not survive multiple-testing correction."
    return f"Unproven, not significant: {body}), no better than chance."


def project(asset: Asset, e: TransitEvent, r: PatternResult, cond: Conditions | None = None) -> Projection | None:
    """One projection from one pattern's evidence; None if the pattern has no headline to project."""
    stat = headline_stat(r)
    if stat is None or r.dominant_outcome not in RATE:
        return None
    name = RATE[r.dominant_outcome]
    rate, base = getattr(stat, f"{name}_rate"), getattr(stat, f"base_{name}_rate")
    q = getattr(stat, f"q_{name}")
    lo, hi = wilson_interval(rate, stat.n)
    return Projection(
        id=projection_id(asset, r.pattern_id, e),
        asset=asset,
        event=e,
        pattern_id=r.pattern_id,
        description=r.description,
        label=r.label,
        score=r.score,
        horizon_days=stat.horizon_days,
        outcome=r.dominant_outcome,
        n=stat.n,
        hit_rate=rate,
        base_rate=base,
        lift=rate / base if base > 0 else None,
        ci_low=lo,
        ci_high=hi,
        q_value=q,
        mean_return=stat.mean_return,
        win_rate=stat.win_rate,
        timing_headline_hours=r.timing_headline_hours,
        timing_dominant=r.timing_dominant,
        timing_label=r.timing_label,
        median_hours_to_move=r.median_hours_to_move,
        window_start=event_moment(e),
        window_end=window_end(asset, e.date, stat.horizon_days),
        like_now=like_now(r, r.dominant_outcome, cond),
        trusted=r.label in TRUSTED,
        note=_note(r.label, r.dominant_outcome, stat.n, rate, base, stat.horizon_days, q),
    )


def group_overlaps(projections: list[Projection]) -> list[Projection]:
    """Per asset, group projections whose windows overlap (in place). A group starts
    at its earliest projection (the anchor) and takes every later one that starts
    inside the anchor's [start day, end day] window, so all members overlap the
    anchor. Not chained transitively: Moon events come almost daily and would chain
    two months into one meaningless group. A group with both a BIG_UP and a
    BIG_DOWN is conflicting: the evidence points both ways over the same days."""
    by_asset: dict[Asset, list[Projection]] = {}
    for p in projections:
        by_asset.setdefault(p.asset, []).append(p)
    for asset, rows in by_asset.items():
        rows.sort(key=lambda p: (p.window_start, p.pattern_id))
        groups: list[list[Projection]] = []
        end = None
        for p in rows:
            if end is not None and utc_day(p.window_start) <= end:
                groups[-1].append(p)
            else:
                groups.append([p])
                end = p.window_end
        for g in groups:
            gid = f"{asset.value}:{utc_day(g[0].window_start):%Y-%m-%d}"  # unique: groups never share a start day
            conflict = {Outcome.BIG_UP, Outcome.BIG_DOWN} <= {p.outcome for p in g}
            for p in g:
                p.group_id, p.conflict = gid, conflict
    return projections


def build_projections(
    events: list[TransitEvent],
    playbooks: dict[Asset, AssetPlaybook | None],
    now: datetime,
    days_ahead: int = DAYS_AHEAD,
    include_none: bool = False,
    conditions: dict[Asset, Conditions] | None = None,
) -> list[Projection]:
    """Every event between now and now + days_ahead, for every asset with a playbook,
    projected from its best-evidenced pattern (label first, then score). Sorted by window start."""
    now = _utc(now)
    until = now + timedelta(days=days_ahead)
    upcoming = [e for e in events if now <= event_moment(e) <= until]
    floor = RANK[ConfidenceLabel.NONE] if include_none else RANK[ConfidenceLabel.WEAK]
    conditions = conditions or {}
    out: list[Projection] = []
    for asset, pb in playbooks.items():
        if pb is None:
            continue
        usable = {r.pattern_id: r for r in pb.patterns if RANK[r.label] >= floor and headline_stat(r) is not None}
        for e in upcoming:
            candidates = [usable[pid] for pid in patterns_for_event(e) if pid in usable]
            if not candidates:
                continue
            best = max(candidates, key=lambda r: (RANK[r.label], r.score, r.n_events))
            p = project(asset, e, best, conditions.get(asset))
            if p is not None:
                out.append(p)
    group_overlaps(out)
    out.sort(key=lambda p: (p.window_start, p.asset.value, p.pattern_id))
    return out
