"""Live side of the strategy: turn new divergences into suggestions, expire the
ones nobody decided on, and follow every suggestion to its outcome.

Called by the runner after each data refresh. A suggestion appears when a
divergence confirms on the latest *completed* daily bar; its entry is that
bar's close (the price you see when the suggestion arrives). For outcomes,
the fill is the next bar's open, exactly as in the backtest, so live results
and backtest expectations are measured the same way.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from orbit.config.settings import SUGGESTION_EXPIRY_BARS
from orbit.core.types import Asset, Decision, Direction, Signal, TradeSuggestion
from orbit.analysis.series import PriceSeries, day64, load_price_series
from orbit.backtest.engine import cost_for, features_at, result, walk
from orbit.journal import store
from orbit.journal.store import Outcome, SuggestionRecord
from orbit.strategy import calibrate
from orbit.strategy import rsi_divergence as strat
from orbit.features.regime import trend_values

ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL, Asset.SILVER]


def _to_dt(d) -> datetime:
    return datetime.fromisoformat(str(d)).replace(tzinfo=timezone.utc)


def _suggestion(asset: Asset, series: PriceSeries, s: strat.DivergenceSignal) -> SuggestionRecord | None:
    entry = float(series.close[s.signal_index])
    lv = strat.levels(s, entry)
    if lv is None:
        return None
    stop, target = lv
    feats = features_at(series, s)
    conf = calibrate.confidence(feats, s.direction.value)
    trend = trend_values(series.close)[s.signal_index]
    when = _to_dt(series.dates[s.signal_index])
    sign = 1 if s.direction == Direction.LONG else -1
    signals = [
        Signal(name="rsi_divergence", asset=asset, timestamp=when, direction=s.direction,
               strength=float(min(1.0, s.rsi_difference / 20)), reason=strat.reason(s, series)),
    ]
    if not np.isnan(trend) and trend != 0:
        agrees = trend * sign > 0
        signals.append(Signal(name="trend", asset=asset, timestamp=when, direction=s.direction if agrees else (Direction.SHORT if sign > 0 else Direction.LONG),
                              strength=0.5, reason=f"50/200-day trend is {'with' if agrees else 'against'} this trade (context only; not part of the rule)."))
    sug = TradeSuggestion(asset=asset, timestamp=when, direction=s.direction, confidence=conf, entry_price=entry, stop_loss=stop, take_profit=target, signals=signals)
    return SuggestionRecord(
        id=f"{asset.value}-{series.dates[s.signal_index]}-{s.direction.value}",
        created_at=datetime.now(timezone.utc),
        signal_date=str(series.dates[s.signal_index]),
        risk_reward=abs(target - entry) / abs(entry - stop),
        suggestion=sug,
        features=feats,
    )


def _follow(asset: Asset, series: PriceSeries, rec: SuggestionRecord, entry_override: tuple[float, float, float] | None = None) -> Outcome | None:
    i = int(np.searchsorted(series.dates, np.datetime64(rec.signal_date, "D")))
    e = i + 1
    if e >= len(series):
        return None
    s = rec.suggestion
    entry = float(series.open[e])
    stop, target = s.stop_loss, s.take_profit
    if entry_override:
        entry, stop, target = entry_override
    out = walk(series, s.direction, e, entry, stop, target, cost_for(asset))
    if out is None:
        return None
    k, price, why = out
    ret, r = result(s.direction, entry, stop, float(price), cost_for(asset))
    return Outcome(entry_date=str(series.dates[e]), entry=entry, exit_date=str(series.dates[k]), exit_price=float(price), reason=why, return_pct=ret, r_multiple=r)


def refresh(series_by_asset: dict[Asset, PriceSeries] | None = None) -> dict[str, int]:
    """Create new suggestions, expire stale ones, resolve outcomes. Returns counts."""
    series_by_asset = series_by_asset or {a: load_price_series(a) for a in ASSETS}
    signals = {a: strat.find_signals(s) for a, s in series_by_asset.items() if len(s) >= 300}
    with store.locked():
        counts = _refresh_locked(series_by_asset, signals)
    return counts


def _refresh_locked(series_by_asset: dict[Asset, PriceSeries], signals: dict) -> dict[str, int]:
    records = store.load()
    known = {r.id for r in records}
    counts = {"new": 0, "expired": 0, "resolved": 0}
    for asset, series in series_by_asset.items():
        if len(series) < 300:
            continue
        last = len(series) - 1
        for s in signals[asset]:
            if s.signal_index != last:
                continue
            rec = _suggestion(asset, series, s)
            if rec and rec.id not in known:
                records.append(rec)
                known.add(rec.id)
                counts["new"] += 1
        for rec in records:
            if rec.suggestion.asset != asset:
                continue
            i = int(np.searchsorted(series.dates, day64(_to_dt(rec.signal_date))))
            if rec.status == "pending" and last - i >= SUGGESTION_EXPIRY_BARS:
                rec.status = "expired"
                counts["expired"] += 1
            if rec.paper is None:
                rec.paper = _follow(asset, series, rec)
                counts["resolved"] += rec.paper is not None
            if rec.decision in (Decision.TAKEN, Decision.MODIFIED) and rec.acted is None:
                override = None
                if rec.decision == Decision.MODIFIED:
                    override = (rec.acted_entry, rec.acted_stop, rec.acted_target)
                rec.acted = _follow(asset, series, rec, override)
    store.save(records)
    return counts


def decide(sid: str, decision: Decision, notes: str, entry: float | None, stop: float | None, target: float | None) -> SuggestionRecord:
    with store.locked():
        records = store.load()
        rec = store.get(records, sid)
        if rec is None:
            raise KeyError(sid)
        if rec.status != "pending":
            raise ValueError(f"suggestion {sid} is already {rec.status}")
        s = rec.suggestion
        rec.status, rec.decision, rec.decided_at, rec.notes = "decided", decision, datetime.now(timezone.utc), notes
        rec.acted_entry = entry if decision == Decision.MODIFIED and entry else s.entry_price
        rec.acted_stop = stop if decision == Decision.MODIFIED and stop else s.stop_loss
        rec.acted_target = target if decision == Decision.MODIFIED and target else s.take_profit
        store.save(records)
    return rec
