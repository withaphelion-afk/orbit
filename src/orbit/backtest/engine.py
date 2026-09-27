"""Replay the strategy over each asset's full history, with costs.

For every divergence signal (strategy/rsi_divergence.py): enter at the next
bar's open, then walk forward bar by bar until the stop, the target or the
time limit. If a bar touches both stop and target, the stop is assumed to have
hit first (the conservative reading of a daily bar). If a bar opens beyond a
level, the trade exits at that open. One trade at a time per asset: a signal
that arrives while a trade is open is skipped.

Returns are net of costs (BACKTEST_COST per side, plus slippage) and also
expressed as R multiples (the result divided by the risk taken), which is
what the drift check and the feedback loop compare against.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import numpy as np

from orbit.config.settings import BACKTEST_COST_PER_SIDE, BACKTEST_SLIPPAGE, DATA_DIR
from orbit.core.types import Asset, Direction
from orbit.analysis.series import PriceSeries
from orbit.features.regime import trend_values
from orbit.features.technical import technical_arrays
from orbit.strategy import rsi_divergence as strat

BACKTEST_DIR = DATA_DIR / "strategy" / "backtest"


@dataclass
class Trade:
    asset: str
    direction: str
    signal_date: str
    entry_date: str
    entry: float
    stop: float
    target: float
    exit_date: str | None
    exit_price: float | None
    exit_reason: str | None  # target / stop / time / open
    return_pct: float | None  # net of costs
    r_multiple: float | None
    bars_held: int | None
    # Features known at the signal bar (the feedback loop learns from these).
    rsi_first: float
    rsi_second: float
    rsi_difference: float
    price_change: float
    bars_between: int
    atr_pct: float
    volatility_pct: float  # 20d realised vol percentile vs history up to then
    trend_aligned: float  # +1 trend agrees with the trade, -1 against, 0 choppy


def cost_for(asset: Asset) -> float:
    return BACKTEST_COST_PER_SIDE.get(asset.value, 0.001) + BACKTEST_SLIPPAGE


def features_at(series: PriceSeries, s: strat.DivergenceSignal) -> dict:
    close = series.close
    vol = technical_arrays(close)["volatility_20d"]
    past = vol[: s.signal_index + 1]
    past = past[~np.isnan(past)]
    vol_pct = float((past < past[-1]).mean()) if len(past) > 20 else 0.5
    trend = trend_values(close)[s.signal_index]
    sign = 1 if s.direction == Direction.LONG else -1
    return {
        "rsi_first": s.rsi_first,
        "rsi_second": s.rsi_second,
        "rsi_difference": s.rsi_difference,
        "price_change": s.price_change,
        "bars_between": s.bars_between,
        "atr_pct": s.atr / close[s.signal_index],
        "volatility_pct": vol_pct,
        "trend_aligned": 0.0 if np.isnan(trend) else float(trend * sign),
    }


def walk(series: PriceSeries, direction: Direction, start: int, entry: float, stop: float, target: float, cost: float):
    """Follow a trade from bar `start` (the entry bar). Returns (exit index, price, reason) or None if still open."""
    long = direction == Direction.LONG
    last = min(len(series) - 1, start + strat.MAX_BARS - 1)
    for k in range(start, last + 1):
        o, h, lo = series.open[k], series.high[k], series.low[k]
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
    if start + strat.MAX_BARS - 1 <= len(series) - 1:
        return last, series.close[last], "time"
    return None


def result(direction: Direction, entry: float, stop: float, exit_price: float, cost: float) -> tuple[float, float]:
    sign = 1 if direction == Direction.LONG else -1
    gross = sign * (exit_price / entry - 1)
    net = gross - 2 * cost
    risk = abs(entry - stop) / entry
    return net * 100, net / risk if risk else 0.0


def run(asset: Asset, series: PriceSeries) -> list[Trade]:
    cost = cost_for(asset)
    trades: list[Trade] = []
    busy_until = -1
    for s in strat.find_signals(series):
        e = s.signal_index + 1
        if e >= len(series) or e <= busy_until:
            continue
        entry = float(series.open[e])
        lv = strat.levels(s, entry)
        if lv is None:
            continue
        stop, target = lv
        out = walk(series, s.direction, e, entry, stop, target, cost)
        feats = features_at(series, s)
        if out is None:
            trades.append(Trade(asset.value, s.direction.value, str(series.dates[s.signal_index]), str(series.dates[e]), entry, stop, target,
                                None, None, "open", None, None, None, **feats))
            busy_until = len(series)
            continue
        k, price, why = out
        ret, r = result(s.direction, entry, stop, float(price), cost)
        trades.append(Trade(asset.value, s.direction.value, str(series.dates[s.signal_index]), str(series.dates[e]), entry, stop, target,
                            str(series.dates[k]), float(price), why, ret, r, k - e + 1, **feats))
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
        "equity_r": [{"date": t.exit_date, "r": float(e)} for t, e in zip(closed, equity)],
    }


def run_all(series_by_asset: dict[Asset, PriceSeries]) -> dict:
    """Backtest every asset, save each (and a pooled summary). Returns the pooled summary."""
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
    pooled: list[Trade] = []
    per_asset = {}
    for asset, series in series_by_asset.items():
        if len(series) < 300:
            continue
        trades = run(asset, series)
        pooled += trades
        summary = summarise(trades)
        per_asset[asset.value] = {k: v for k, v in summary.items() if k != "equity_r"}
        (BACKTEST_DIR / f"{asset.value}.json").write_text(
            json.dumps({"asset": asset.value, "strategy": strat.NAME, "summary": summary, "trades": [asdict(t) for t in trades]}, indent=1),
            encoding="utf-8",
        )
    pooled_summary = summarise(sorted(pooled, key=lambda t: t.exit_date or "9999"))
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": strat.NAME,
        "parameters": {
            "rsi_period": strat.RSI_PERIOD, "pivot_left": strat.PIVOT_LEFT, "pivot_right": strat.PIVOT_RIGHT,
            "bars_between": [strat.MIN_BARS_BETWEEN, strat.MAX_BARS_BETWEEN], "bull_rsi_zone": strat.BULL_RSI_ZONE,
            "bear_rsi_zone": strat.BEAR_RSI_ZONE, "stop_atr": strat.STOP_ATR, "target_r": strat.TARGET_R, "max_bars": strat.MAX_BARS,
            "costs_per_side": BACKTEST_COST_PER_SIDE, "slippage": BACKTEST_SLIPPAGE,
        },
        "pooled": pooled_summary,
        "assets": per_asset,
    }
    (BACKTEST_DIR / "summary.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def load(asset: str | None = None) -> dict | None:
    path = BACKTEST_DIR / (f"{asset}.json" if asset else "summary.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def load_trades() -> list[Trade]:
    out = []
    for path in BACKTEST_DIR.glob("*.json"):
        if path.name == "summary.json":
            continue
        out += [Trade(**t) for t in json.loads(path.read_text(encoding="utf-8"))["trades"]]
    return out
