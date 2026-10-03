"""Drift: is the strategy doing live what the backtest said it would?

Live = every suggestion the strategy has made since it went live, followed to
its outcome with the strategy's own levels (whether or not you took it), so
the check measures the system, not your choices. Expected = the pooled
backtest. The win-rate gap is expressed as a z-score; at DRIFT_WATCH_Z it's
"WATCH", at DRIFT_SCALE_DOWN_Z it's "DRIFT" (the point to scale down).

The curve is cumulative R per live trade against what the backtest expects
(its average R per trade), with a 1-sigma band from the backtest's spread.
"""

from __future__ import annotations

import math

import numpy as np

from orbit.config.settings import DRIFT_SCALE_DOWN_Z, DRIFT_WATCH_Z
from orbit.backtest.engine import load as load_backtest
from orbit.journal import store

MIN_TRADES_FOR_STATUS = 10


def report(timeframe: str = "1d") -> dict | None:
    """Live vs backtest for one timeframe (4H and 1D are tracked apart)."""
    bt = load_backtest()
    exp = ((bt or {}).get("timeframes", {}).get(timeframe) or {}).get("pooled")
    if not exp or not exp.get("trades"):
        return None
    live = sorted((r for r in store.load() if r.paper is not None and r.timeframe == timeframe), key=lambda r: r.paper.exit_date)
    r_live = np.array([r.paper.r_multiple for r in live])
    n = len(r_live)
    ew, er, sr = exp["win_rate"], exp["avg_r"], exp["std_r"]
    lw = float((r_live > 0).mean()) if n else 0.0
    z = (lw - ew) / math.sqrt(ew * (1 - ew) / n) if n and 0 < ew < 1 else 0.0
    status = "OK"
    if n >= MIN_TRADES_FOR_STATUS:
        status = "DRIFT" if abs(z) >= DRIFT_SCALE_DOWN_Z else "WATCH" if abs(z) >= DRIFT_WATCH_Z else "OK"
    equity = np.cumsum(r_live) if n else np.array([])
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:] if n else np.array([])
    # One point per exit day (charts need unique times): the running totals after that day's last exit.
    by_day: dict[str, int] = {}
    for k, r in enumerate(live):
        by_day[r.paper.exit_date[:10]] = k  # one point per exit day (charts need unique times)
    curve = [
        {"time": f"{d}T00:00:00Z", "expected": float((k + 1) * er), "live": float(equity[k]), "band": float(sr * math.sqrt(k + 1))}
        for d, k in by_day.items()
    ]
    return {
        "timeframe": timeframe,
        "status": status,
        "z_score": float(z),
        "scale_down_at": DRIFT_SCALE_DOWN_Z,
        "min_trades": MIN_TRADES_FOR_STATUS,
        "expected_win_rate": ew,
        "live_win_rate": lw,
        "expected_avg_r": er,
        "live_avg_r": float(r_live.mean()) if n else 0.0,
        "expected_max_dd": exp["max_drawdown_r"],
        "live_max_dd": float((equity - peak).min()) if n else 0.0,
        "backtest_trades": exp["trades"],
        "live_trades": n,
        "curve": curve,
    }
