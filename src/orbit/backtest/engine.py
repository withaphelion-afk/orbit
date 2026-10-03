"""Replay the divergence strategy over each asset's history, per timeframe (4H and 1D), with costs.

Which divergences are traded: the confirmed ones whose OUT-OF-SAMPLE score (from
the model's walk-forward check, so the model never saw what came next) is at or
above the timeframe's alert threshold. Each trade enters at the next bar's open;
the stop is the second swing's extreme (no ATR) and the target DIVERGENCE_TARGET_R
times the risk; it closes after DIVERGENCE_HORIZON_BARS bars of its own timeframe
if neither is hit. A bar that touches both counts as the stop; a gap through a
level exits at the open. One trade at a time per asset and timeframe.

Returns are net of costs (BACKTEST_COST per side, plus slippage) and also given
in R (the result over the risk taken), which drift and the feedback screen use.
4H and 1D results are kept apart: they never mix.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import numpy as np

from orbit.config.settings import BACKTEST_COST_PER_SIDE, BACKTEST_SLIPPAGE, DATA_DIR, DIVERGENCE_HORIZON_BARS, DIVERGENCE_SUGGEST_TIMEFRAMES, DIVERGENCE_TARGET_R
from orbit.core.types import Asset, Direction

BACKTEST_DIR = DATA_DIR / "strategy" / "backtest"
NAME = "RSI divergence (learned), 4H and 1D"


@dataclass
class Trade:
    asset: str
    timeframe: str
    direction: str
    kind: str  # regular / hidden
    signal_date: str  # the confirmation bar (ISO, UTC)
    entry_date: str
    entry: float
    stop: float
    target: float
    exit_date: str | None
    exit_price: float | None
    exit_reason: str | None  # target / stop / time / open
    return_pct: float | None
    r_multiple: float | None
    bars_held: int | None
    score: float | None  # the out-of-sample score that selected it


def iso(t: int | float) -> str:
    return datetime.fromtimestamp(int(t), tz=timezone.utc).isoformat()


def cost_for(asset: Asset) -> float:
    return BACKTEST_COST_PER_SIDE.get(asset.value, 0.001) + BACKTEST_SLIPPAGE


def levels(direction: str, entry: float, swing_extreme: float) -> tuple[float, float] | None:
    """(stop, target): the stop at the second swing's extreme, the target TARGET_R x the risk. None if the entry is past the stop."""
    risk = entry - swing_extreme if direction == "LONG" else swing_extreme - entry
    if risk <= 0:
        return None
    return swing_extreme, entry + DIVERGENCE_TARGET_R * risk if direction == "LONG" else entry - DIVERGENCE_TARGET_R * risk


def _dir(direction) -> str:
    return str(getattr(direction, "value", direction))


def walk(b, direction: Direction | str, start: int, entry: float, stop: float, target: float, max_bars: int):
    """Follow a trade from bar `start` (the entry bar). (exit index, price, reason), or None while still open."""
    long = _dir(direction) == "LONG"
    last = min(len(b) - 1, start + max_bars - 1)
    for k in range(start, last + 1):
        o, h, lo = b.open[k], b.high[k], b.low[k]
        if k > start:  # a gap through a level exits at the open
            if long and o <= stop or not long and o >= stop:
                return k, o, "stop"
            if long and o >= target or not long and o <= target:
                return k, o, "target"
        hit_stop = lo <= stop if long else h >= stop
        hit_target = h >= target if long else lo <= target
        if hit_stop:
            return k, stop, "stop"
        if hit_target:
            return k, target, "target"
    if start + max_bars - 1 <= len(b) - 1:
        return last, b.close[last], "time"
    return None


def result(direction: Direction | str, entry: float, stop: float, exit_price: float, cost: float) -> tuple[float, float]:
    sign = 1 if _dir(direction) == "LONG" else -1
    gross = sign * (exit_price / entry - 1)
    net = gross - 2 * cost
    risk = abs(entry - stop) / entry
    return net * 100, net / risk if risk else 0.0


def run(asset: Asset, timeframe: str, b, candidates: list[dict], threshold: float) -> list[Trade]:
    """Trades for one asset and timeframe from its scored candidates."""
    cost = cost_for(asset)
    max_bars = DIVERGENCE_HORIZON_BARS[timeframe]
    index = {int(t): k for k, t in enumerate(b.time)}
    trades: list[Trade] = []
    busy_until = -1
    for c in sorted(candidates, key=lambda c: c["confirmed_at"]):
        if c["oos_score"] is None or c["oos_score"] < threshold:
            continue
        s = index.get(c["confirmed_at"])
        if s is None:
            continue
        e = s + 1
        if e >= len(b) or e <= busy_until:
            continue
        entry = float(b.open[e])
        lv = levels(c["direction"], entry, c["p2"])
        if lv is None:
            continue
        stop, target = lv
        out = walk(b, c["direction"], e, entry, stop, target, max_bars)
        common = dict(asset=asset.value, timeframe=timeframe, direction=c["direction"], kind=c["kind"], signal_date=iso(b.time[s]),
                      entry_date=iso(b.time[e]), entry=entry, stop=stop, target=target, score=c["oos_score"])
        if out is None:
            trades.append(Trade(**common, exit_date=None, exit_price=None, exit_reason="open", return_pct=None, r_multiple=None, bars_held=None))
            busy_until = len(b)
            continue
        k, price, why = out
        ret, r = result(c["direction"], entry, stop, float(price), cost)
        trades.append(Trade(**common, exit_date=iso(b.time[k]), exit_price=float(price), exit_reason=why, return_pct=ret, r_multiple=r, bars_held=k - e + 1))
        busy_until = k
    return trades


def summarise(trades: list[Trade]) -> dict:
    closed = [t for t in trades if t.r_multiple is not None]
    if not closed:
        return {"trades": 0}
    r = np.array([t.r_multiple for t in closed])
    rets = np.array([t.return_pct for t in closed])
    equity = np.cumsum(r)
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    wins, losses = r[r > 0], r[r <= 0]
    years: dict[str, dict] = {}
    for t in closed:
        y = years.setdefault(t.exit_date[:4], {"trades": 0, "wins": 0, "r": 0.0})
        y["trades"] += 1
        y["wins"] += int(t.r_multiple > 0)
        y["r"] += t.r_multiple
    by_dir = {}
    for d in ("LONG", "SHORT"):
        rd = np.array([t.r_multiple for t in closed if t.direction == d])
        by_dir[d] = {"trades": int(len(rd)), "win_rate": float((rd > 0).mean()) if len(rd) else None, "avg_r": float(rd.mean()) if len(rd) else None}
    return {
        "trades": len(closed),
        "open": len(trades) - len(closed),
        "win_rate": float((r > 0).mean()),
        "avg_r": float(r.mean()),
        "std_r": float(r.std()),
        "avg_return_pct": float(rets.mean()),
        "profit_factor": float(wins.sum() / -losses.sum()) if losses.sum() < 0 else None,
        "total_r": float(r.sum()),
        "max_drawdown_r": float((equity - peak).min()),
        "avg_bars_held": float(np.mean([t.bars_held for t in closed])),
        "exit_reasons": {k: sum(1 for t in closed if t.exit_reason == k) for k in ("target", "stop", "time")},
        "by_direction": by_dir,
        "by_year": years,
        "equity_r": [{"date": t.exit_date[:10], "r": float(e)} for t, e in zip(closed, equity)],
    }


def run_all(model_report: dict, rows) -> dict:
    """Backtest every asset on each suggestion timeframe from the model's rows. Saves each, plus a summary per timeframe."""
    from orbit.strategy import divergence_model as dm

    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
    oos = model_report.get("oos_scores", {})
    by_series: dict[tuple[str, str], tuple] = {}
    for r in rows:
        if r.cand.confirm is None or r.tf not in DIVERGENCE_SUGGEST_TIMEFRAMES:
            continue
        b, c = r.ctx.b, r.cand
        by_series.setdefault((r.asset, r.tf), (b, []))[1].append(
            {"direction": c.direction, "kind": c.kind, "confirmed_at": int(b.time[c.confirm]), "p2": c.p2, "oos_score": oos.get(r.id)})
    timeframes = {}
    for tf in DIVERGENCE_SUGGEST_TIMEFRAMES:
        threshold = model_report.get("thresholds", {}).get(tf, 1.0)
        pooled: list[Trade] = []
        per_asset = {}
        for asset in dm.ASSETS:
            if (asset.value, tf) not in by_series:
                continue
            b, cands = by_series[(asset.value, tf)]
            trades = run(asset, tf, b, cands, threshold)
            pooled += trades
            summary = summarise(trades)
            per_asset[asset.value] = {k: v for k, v in summary.items() if k != "equity_r"}
            (BACKTEST_DIR / f"{asset.value}_{tf}.json").write_text(
                json.dumps({"asset": asset.value, "timeframe": tf, "strategy": NAME, "summary": summary, "trades": [asdict(t) for t in trades]}, indent=1),
                encoding="utf-8")
        timeframes[tf] = {"pooled": summarise(sorted(pooled, key=lambda t: t.exit_date or "9999")), "assets": per_asset, "threshold": threshold}
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": NAME,
        "parameters": {"target_r": DIVERGENCE_TARGET_R, "max_bars": DIVERGENCE_HORIZON_BARS, "costs_per_side": BACKTEST_COST_PER_SIDE,
                       "slippage": BACKTEST_SLIPPAGE, "selection": "confirmed divergences whose out-of-sample score reached the alert threshold"},
        "timeframes": timeframes,
        # The daily results also stay at the top level, for anything that reads a single timeframe.
        "pooled": timeframes.get("1d", {}).get("pooled", {"trades": 0}),
        "assets": timeframes.get("1d", {}).get("assets", {}),
    }
    (BACKTEST_DIR / "summary.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def load(asset: str | None = None, timeframe: str = "1d") -> dict | None:
    path = BACKTEST_DIR / (f"{asset}_{timeframe}.json" if asset else "summary.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
