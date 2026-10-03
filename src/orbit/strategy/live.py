"""Live side of the strategy: turn new alerting divergences into suggestions,
expire the ones nobody decided on, and follow every suggestion to its outcome.

Called by the runner after the model has scored the latest bars. A suggestion
appears when a divergence on a suggestion timeframe (DIVERGENCE_SUGGEST_TIMEFRAMES:
4H and 1D) confirms on the latest completed bar with a score at or above its
timeframe's alert threshold. Entry: that bar's close. Stop: the second swing's
extreme (no ATR). Target: DIVERGENCE_TARGET_R x the risk. An undecided suggestion
expires after SUGGESTION_EXPIRY_BARS bars of its own timeframe (12 hours on 4H,
3 days on 1D). Outcomes are followed on that timeframe's bars, filled at the
next bar's open, exactly as in the backtest.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from orbit.config.settings import DIVERGENCE_HORIZON_BARS, DIVERGENCE_SUGGEST_TIMEFRAMES, SUGGESTION_EXPIRY_BARS
from orbit.core.types import Asset, Decision, Direction, Signal, TradeSuggestion
from orbit.backtest.engine import cost_for, iso, levels, result, walk
from orbit.journal import store
from orbit.journal.store import Outcome, SuggestionRecord
from orbit.strategy import bars as bars_mod

ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL, Asset.SILVER]
TF_LABEL = {"1h": "1H", "4h": "4H", "1d": "1D", "1w": "1W"}


def _epoch(text: str) -> int:
    t = datetime.fromisoformat(text)
    return int((t if t.tzinfo else t.replace(tzinfo=timezone.utc)).timestamp())


def _reason(c: dict, asset: Asset, tf: str) -> str:
    bull = c["direction"] == "LONG"
    what = ("lower low" if bull else "higher high") if c["kind"] == "regular" else ("higher low" if bull else "lower high")
    rsi_what = ("higher low" if bull else "lower high") if c["kind"] == "regular" else ("lower low" if bull else "higher high")
    return (f"{c['kind'].capitalize()} {'bullish' if bull else 'bearish'} RSI divergence on {TF_LABEL[tf]}: price made a {what} "
            f"({c['p1']:,.4g} -> {c['p2']:,.4g}) while RSI(14) made a {rsi_what} ({c['r1']:.1f} -> {c['r2']:.1f}).")


def _suggestion(asset: Asset, tf: str, b, c: dict, trusted: bool) -> SuggestionRecord | None:
    k = int(np.searchsorted(b.time, c["confirmed_at"]))
    entry = float(b.close[k])
    lv = levels(c["direction"], entry, c["p2"])
    if lv is None:
        return None
    stop, target = lv
    when = datetime.fromtimestamp(c["confirmed_at"], tz=timezone.utc)
    direction = Direction(c["direction"])
    signals = [Signal(name="rsi_divergence", asset=asset, timestamp=when, direction=direction, strength=float(min(1.0, c["score"])),
                      reason=_reason(c, asset, tf)),
               Signal(name="model", asset=asset, timestamp=when, direction=direction, strength=float(c["score"]),
                      reason=f"Learned score {c['score']:.0%}" + ("" if trusted else " (unproven: the model hasn't beaten the plain rate yet)"))]
    sug = TradeSuggestion(asset=asset, timestamp=when, direction=direction, confidence=float(c["score"]), entry_price=entry,
                          stop_loss=stop, take_profit=target, signals=signals)
    return SuggestionRecord(
        id=f"{asset.value}-{tf}-{iso(c['confirmed_at'])[:16]}-{c['direction']}",
        created_at=datetime.now(timezone.utc),
        signal_date=iso(c["confirmed_at"]),
        timeframe=tf,
        risk_reward=abs(target - entry) / abs(entry - stop),
        suggestion=sug,
        features={"score": float(c["score"]), "r1": c["r1"], "r2": c["r2"]},
        divergence_id=c["id"],
    )


def _follow(asset: Asset, b, rec: SuggestionRecord, override: tuple[float, float, float] | None = None) -> Outcome | None:
    k = int(np.searchsorted(b.time, _epoch(rec.signal_date)))
    e = k + 1
    if e >= len(b):
        return None
    s = rec.suggestion
    entry, stop, target = float(b.open[e]), s.stop_loss, s.take_profit
    if override:
        entry, stop, target = override
    out = walk(b, s.direction, e, entry, stop, target, DIVERGENCE_HORIZON_BARS.get(rec.timeframe, 30))
    if out is None:
        return None
    x, price, why = out
    ret, r = result(s.direction, entry, stop, float(price), cost_for(asset))
    return Outcome(entry_date=iso(b.time[e]), entry=entry, exit_date=iso(b.time[x]), exit_price=float(price), reason=why, return_pct=ret, r_multiple=r)


def refresh(recent: dict | None = None, bars: dict | None = None) -> dict[str, int]:
    """Create suggestions from the latest alerts, expire stale ones, resolve outcomes. Returns counts."""
    from orbit.strategy import divergence_model as dm

    recent = recent if recent is not None else (dm.load_recent() or {"candidates": {}})
    trusted = bool(recent.get("trusted"))
    loaded = bars or {}

    def get_bars(asset: Asset, tf: str):
        if (asset, tf) not in loaded:
            loaded[(asset, tf)] = bars_mod.load(asset, tf)
        return loaded[(asset, tf)]

    counts = {"new": 0, "expired": 0, "resolved": 0}
    with store.locked():
        records = store.load()
        known = {r.id for r in records}
        for asset in ASSETS:
            for tf in DIVERGENCE_SUGGEST_TIMEFRAMES:
                cands = recent.get("candidates", {}).get(asset.value, {}).get(tf, [])
                if not cands:
                    continue
                b = get_bars(asset, tf)
                if not len(b):
                    continue
                last = int(b.time[-1])
                for c in cands:
                    if c.get("alert") and c.get("confirmed_at") == last:
                        rec = _suggestion(asset, tf, b, c, trusted)
                        if rec and rec.id not in known:
                            records.append(rec)
                            known.add(rec.id)
                            counts["new"] += 1
        for rec in records:
            asset, tf = rec.suggestion.asset, rec.timeframe
            b = get_bars(asset, tf)
            if not len(b):
                continue
            k = int(np.searchsorted(b.time, _epoch(rec.signal_date)))
            if rec.status == "pending" and len(b) - 1 - k >= SUGGESTION_EXPIRY_BARS:
                rec.status = "expired"
                counts["expired"] += 1
            if rec.paper is None:
                rec.paper = _follow(asset, b, rec)
                counts["resolved"] += rec.paper is not None
            if rec.decision in (Decision.TAKEN, Decision.MODIFIED) and rec.acted is None:
                override = (rec.acted_entry, rec.acted_stop, rec.acted_target) if rec.decision == Decision.MODIFIED else None
                rec.acted = _follow(asset, b, rec, override)
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
