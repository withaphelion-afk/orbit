"""The self-learning divergence model: the market grades every divergence, you teach it, it retrains every run.

    candidates   strategy/divergence.py on 1H/4H/1D/1W for every asset
    features     what was known on the confirmation bar (FEATURES below)
    labels       worked: price moved the asset's top-25% move for that timeframe in
                 the divergence's direction within HORIZON bars, before moving the same
                 distance the wrong way. Failed otherwise. Too recent: no label yet.
                 Your ✓ real / ✗ not real (journal/divergence_labels.json) override
                 the market's grade for that candidate and count USER_WEIGHT times.
    model        ridge logistic regression in numpy, retrained on every runner cycle
    trust        walk-forward: trained on earlier candidates, scored on later ones. Trusted
                 only if that beats always predicting the base rate (Brier score); until
                 then every score is shown as "unproven"
    alerts       a confirmed candidate whose score is in the top ALERT_QUANTILE of its
                 timeframe's scores. 4H and 1D alerts also become Take/Skip suggestions

Writes data/strategy/divergence_model.json (the weights the browser scores with,
plus the trust check) and data/strategy/divergences.json (recent candidates per
asset and timeframe, scored, for the chart, the alerts list and the API).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from orbit.analysis.model import _sigmoid, auc, fit_logistic, log_loss
from orbit.config.settings import (
    DATA_DIR,
    DIVERGENCE_ALERT_QUANTILE,
    DIVERGENCE_HORIZON_BARS,
    DIVERGENCE_TRAIN_BARS,
    DIVERGENCE_USER_WEIGHT,
)
from orbit.core.types import Asset
from orbit.fsutil import atomic_write_text
from orbit.strategy import bars as bars_mod
from orbit.strategy import divergence as det

STRATEGY_DIR = DATA_DIR / "strategy"
MODEL_PATH = STRATEGY_DIR / "divergence_model.json"
RECENT_PATH = STRATEGY_DIR / "divergences.json"
LABELS_PATH = DATA_DIR / "journal" / "divergence_labels.json"
ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL, Asset.SILVER]
RECENT_BARS = 1000
MOVE_QUANTILE = 0.75
LAMBDA = 5.0
WF_FOLDS = 5

FEATURES = [
    "rsi_first", "rsi_second", "first_extreme", "rsi_change", "price_change", "disagreement", "bars_between",
    "strength_first", "strength_second", "hidden", "long", "volume_trend", "trend_before", "regime", "volatility_pct",
    "tf_1h", "tf_4h", "tf_1d", "tf_1w", "asset_btc", "asset_eth", "asset_sol", "asset_silver",
]


def candidate_id(asset: str, tf: str, t1: int, t2: int, direction: str) -> str:
    return f"{asset}|{tf}|{t1}|{t2}|{direction}"


# ---------------------------------------------------------------- context arrays per series


@dataclass
class Context:
    b: bars_mod.Bars
    vol_ma5: np.ndarray
    vol_ma20: np.ndarray
    vol_pct: np.ndarray  # 20-bar return volatility, as a percentile of the previous 500 bars
    move: float  # the asset's top-25% absolute move over HORIZON bars for this timeframe
    regime: np.ndarray  # +1 / -1 / 0 market trend (the BTC 50/200-day gate for crypto, silver's own)


def _rolling_mean(x: np.ndarray, n: int) -> np.ndarray:
    c = np.cumsum(np.r_[0.0, x])
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def _context(b: bars_mod.Bars, regime_by_time) -> Context:
    close = b.close
    ret = np.r_[np.nan, np.diff(np.log(close))]
    sq = _rolling_mean(np.nan_to_num(ret) ** 2, 20)
    vol = np.sqrt(sq)
    pct = np.full(len(close), 0.5)
    for k in range(40, len(close)):
        past = vol[max(19, k - 500):k + 1]
        pct[k] = float((past < vol[k]).mean())
    h = DIVERGENCE_HORIZON_BARS[b.timeframe]
    moves = np.abs(close[h:] / close[:-h] - 1) if len(close) > h else np.array([0.05])
    return Context(b, _rolling_mean(b.volume, 5), _rolling_mean(b.volume, 20), pct, float(np.quantile(moves, MOVE_QUANTILE)), regime_by_time(b.time))


def features(c: det.Candidate, ctx: Context) -> list[float]:
    b = ctx.b
    sign = 1.0 if c.direction == "LONG" else -1.0
    k = c.confirm if c.confirm is not None else len(b) - 1
    price_change = (c.p2 / c.p1 - 1) * sign
    rsi_change = (c.r2 - c.r1) * sign
    start = max(0, c.i - 20)
    trend_before = (b.close[c.i] / b.close[start] - 1) * sign if c.i > start else 0.0
    v5, v20 = ctx.vol_ma5[k], ctx.vol_ma20[k]
    volume_trend = math.log((v5 + 1e-9) / (v20 + 1e-9)) if v20 and not math.isnan(v20) and not math.isnan(v5) else 0.0
    extreme = 1.0 if (c.direction == "LONG" and c.r1 < 30) or (c.direction == "SHORT" and c.r1 > 70) else 0.0
    tf = b.timeframe
    a = b.asset.value
    return [
        c.r1 / 100, c.r2 / 100, extreme, rsi_change / 100, price_change, math.copysign(math.log1p(abs(rsi_change) / (abs(price_change) * 100 + 1)), rsi_change),
        (c.j - c.i) / 60, math.log1p(c.s1), math.log1p(c.s2), 1.0 if c.kind == "hidden" else 0.0, 1.0 if c.direction == "LONG" else 0.0,
        volume_trend, trend_before, float(ctx.regime[k]) * sign, float(ctx.vol_pct[k]),
        float(tf == "1h"), float(tf == "4h"), float(tf == "1d"), float(tf == "1w"),
        float(a == "BTC"), float(a == "ETH"), float(a == "SOL"), float(a == "SILVER"),
    ]


def label(c: det.Candidate, ctx: Context) -> int | None:
    """1 worked, 0 failed, None not resolvable yet."""
    if c.confirm is None:
        return None
    b, k = ctx.b, c.confirm
    entry = b.close[k]
    h = DIVERGENCE_HORIZON_BARS[b.timeframe]
    for t in range(k + 1, min(len(b), k + 1 + h)):
        up, down = b.high[t] / entry - 1, 1 - b.low[t] / entry
        good, bad = (up, down) if c.direction == "LONG" else (down, up)
        if bad >= ctx.move:
            return 0  # the wrong way first (or both on one bar: counted as failed)
        if good >= ctx.move:
            return 1
    return 0 if k + h < len(b) else None


# ---------------------------------------------------------------- regimes


def _regime_lookup():
    """time -> +1/-1/0 market trend, from BTC's daily 50/200-day trend (crypto) or silver's own."""
    from orbit.features.regime import trend_values

    tables = {}
    for asset in (Asset.BTC, Asset.SILVER):
        d = bars_mod.load(asset, "1d")
        tables[asset] = (d.time, np.nan_to_num(trend_values(d.close)))

    def make(asset: Asset):
        times, vals = tables[Asset.SILVER if asset == Asset.SILVER else Asset.BTC]

        def at(t: np.ndarray) -> np.ndarray:
            idx = np.searchsorted(times, t, side="right") - 1
            out = np.zeros(len(t))
            ok = idx >= 0
            out[ok] = vals[idx[ok]]
            return out

        return at

    return make


# ---------------------------------------------------------------- user labels


def load_labels() -> list[dict]:
    try:
        return json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def add_label(asset: str, timeframe: str, t1: int, t2: int, direction: str, verdict: str, note: str = "", source: str = "detected") -> dict:
    """Save your ✓ real / ✗ not real for a divergence (or one it missed). A later label for the same pair replaces the earlier one."""
    from orbit.journal import store

    if verdict not in ("real", "not"):
        raise ValueError("verdict must be 'real' or 'not'")
    rec = {"id": candidate_id(asset, timeframe, t1, t2, direction), "asset": asset, "timeframe": timeframe, "t1": int(t1), "t2": int(t2),
           "direction": direction, "verdict": verdict, "note": note, "source": source, "at": datetime.now(timezone.utc).isoformat()}
    with store.locked():
        labels = [x for x in load_labels() if x.get("id") != rec["id"]] + [rec]
        atomic_write_text(LABELS_PATH, json.dumps(labels, indent=1))
    return rec


# ---------------------------------------------------------------- dataset


@dataclass
class Row:
    id: str
    asset: str
    tf: str
    t: int  # confirmation time
    x: list[float]
    y: int | None  # market grade
    user: str | None  # "real" / "not"
    cand: det.Candidate
    ctx: Context


def build(now: float | None = None) -> list[Row]:
    regime_for = _regime_lookup()
    labels = {x["id"]: x for x in load_labels()}
    rows: list[Row] = []
    for asset in ASSETS:
        for tf in bars_mod.TIMEFRAMES:
            b = bars_mod.load(asset, tf, now)
            cap = DIVERGENCE_TRAIN_BARS.get(tf)
            if cap:
                b = b.tail(cap)
            if len(b) < 100:
                continue
            ctx = _context(b, regime_for(asset))
            found = det.find(b.high, b.low, b.close)
            seen = set()
            for c in found:
                cid = candidate_id(asset.value, tf, int(b.time[c.i]), int(b.time[c.j]), c.direction)
                seen.add(cid)
                k = c.confirm if c.confirm is not None else len(b) - 1
                user = labels.get(cid, {}).get("verdict")
                rows.append(Row(cid, asset.value, tf, int(b.time[k]), features(c, ctx), label(c, ctx), user, c, ctx))
            # Divergences you marked that detection missed: rebuilt from your two swings, counted as real.
            for lab in labels.values():
                if lab["asset"] != asset.value or lab["timeframe"] != tf or lab["id"] in seen or lab.get("source") != "manual":
                    continue
                i, j = int(np.searchsorted(b.time, lab["t1"])), int(np.searchsorted(b.time, lab["t2"]))
                if not (0 <= i < j < len(b)):
                    continue
                low = lab["direction"] == "LONG"
                pr = b.low if low else b.high
                r = det.rsi(b.close)
                if math.isnan(r[i]) or math.isnan(r[j]):
                    continue
                k = min(j + det.RIGHT, len(b) - 1)
                c = det.Candidate("manual", lab["direction"], i, j, k, float(pr[i]), float(pr[j]), float(r[i]), float(r[j]),
                                  det._strength(pr, i, low), det._strength(pr, j, low))
                rows.append(Row(lab["id"], asset.value, tf, int(b.time[k]), features(c, ctx), label(c, ctx), lab["verdict"], c, ctx))
    return rows


def _target(r: Row) -> tuple[float, float] | None:
    """(y, weight) for training: your label wins and counts more; otherwise the market's grade."""
    if r.user:
        return (1.0 if r.user == "real" else 0.0), float(DIVERGENCE_USER_WEIGHT)
    if r.y is None:
        return None
    return float(r.y), 1.0


def _fit(X: np.ndarray, y: np.ndarray, w: np.ndarray) -> dict:
    mu, sd = X.mean(axis=0), X.std(axis=0) + 1e-9
    Z = np.hstack([np.ones((len(X), 1)), (X - mu) / sd])
    # fit_logistic has no sample weights: repeat weighted rows (weights are small integers)
    reps = np.maximum(1, np.round(w).astype(int))
    coef = fit_logistic(np.repeat(Z, reps, axis=0), np.repeat(y, reps), LAMBDA)
    return {"mu": mu.tolist(), "sd": sd.tolist(), "coef": coef.tolist()}


def score(model: dict, X: np.ndarray) -> np.ndarray:
    Z = (X - np.array(model["mu"])) / np.array(model["sd"])
    return _sigmoid(model["coef"][0] + Z @ np.array(model["coef"][1:]))


def train(rows: list[Row] | None = None, now: float | None = None) -> dict:
    """Retrain on everything graded so far plus your labels; check it walk-forward; score every candidate; write both files."""
    rows = build(now) if rows is None else rows
    graded = [(r, t) for r in rows if (t := _target(r)) is not None]
    report: dict = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "RSI divergence (learned)",
        "features": FEATURES,
        "n_market": sum(1 for r, _ in graded if not r.user),
        "n_user": sum(1 for r, _ in graded if r.user),
        "base_rate": None,
        "trusted": False,
        "model": None,
        "thresholds": {},
        "by_timeframe": {},
        "out_of_sample": None,
        "agreement": _agreement(rows),
    }
    if len(graded) < 50:
        report["note"] = f"Only {len(graded)} graded divergences so far; scores are the plain rate until there are 50."
        _write(report, rows, None, {})
        return report
    X = np.array([r.x for r, _ in graded])
    y = np.array([t[0] for _, t in graded])
    w = np.array([t[1] for _, t in graded])
    times = np.array([r.t for r, _ in graded])
    report["base_rate"] = float(np.average(y, weights=w))
    model = _fit(X, y, w)
    report["model"] = model
    report["weights"] = sorted(({"feature": f, "weight": float(c)} for f, c in zip(FEATURES, model["coef"][1:])), key=lambda d: -abs(d["weight"]))

    # Walk-forward: train on everything before each fold's start time, score the fold.
    order = np.argsort(times)
    folds = np.array_split(order, WF_FOLDS + 1)[1:]
    preds, truth, base, oos_ids = [], [], [], []
    oos_scores: dict[str, float] = {}
    for fold in folds:
        cut = times[fold].min()
        tr = times < cut
        if tr.sum() < 50:
            continue
        m = _fit(X[tr], y[tr], w[tr])
        preds.append(score(m, X[fold]))
        truth.append(y[fold])
        base.append(np.full(len(fold), np.average(y[tr], weights=w[tr])))
        oos_ids += [graded[k][0].id for k in fold]
    if preds:
        p, t, c = np.concatenate(preds), np.concatenate(truth), np.concatenate(base)
        edges = np.unique(np.quantile(p, np.linspace(0, 1, 6)))
        buckets = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            m = (p >= lo) & (p <= hi)
            if m.sum():
                buckets.append({"predicted": float(p[m].mean()), "actual": float(t[m].mean()), "n": int(m.sum())})
        oos = {"n": int(len(t)), "brier": float(np.mean((p - t) ** 2)), "brier_base_rate": float(np.mean((c - t) ** 2)),
               "log_loss": log_loss(t, p), "log_loss_base_rate": log_loss(t, c), "auc": auc(t, p), "buckets": buckets}
        report["out_of_sample"] = oos
        report["trusted"] = oos["brier"] < oos["brier_base_rate"]
        oos_scores = dict(zip(oos_ids, p.tolist()))

    # Per timeframe: how many, the base rate, and the alert threshold (top ALERT_QUANTILE of its scores).
    all_scores = score(model, np.array([r.x for r in rows])) if rows else np.array([])
    for tf in bars_mod.TIMEFRAMES:
        idx = [k for k, r in enumerate(rows) if r.tf == tf]
        g = [t for r, t in graded if r.tf == tf]
        if not idx:
            continue
        report["thresholds"][tf] = float(np.quantile(all_scores[idx], DIVERGENCE_ALERT_QUANTILE))
        report["by_timeframe"][tf] = {"candidates": len(idx), "graded": len(g), "worked": float(np.mean([v for v, _ in g])) if g else None}
    _write(report, rows, all_scores, oos_scores)
    report["oos_scores"] = oos_scores  # in memory only, for the backtest
    return report


def _agreement(rows: list[Row]) -> dict:
    both = [r for r in rows if r.user and r.y is not None]
    agree = sum(1 for r in both if (r.user == "real") == (r.y == 1))
    return {"labelled": sum(1 for r in rows if r.user), "compared": len(both), "agree": agree,
            "disagree": [{"id": r.id, "you": r.user, "market": "worked" if r.y == 1 else "failed"} for r in both if (r.user == "real") != (r.y == 1)][:50]}


def _write(report: dict, rows: list[Row], scores: np.ndarray | None, oos: dict[str, float]) -> None:
    STRATEGY_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(MODEL_PATH, json.dumps(report, indent=1))
    recent: dict[str, dict[str, list]] = {}
    for k, r in enumerate(rows):
        b = r.ctx.b
        if r.cand.j < len(b) - RECENT_BARS:
            continue
        c = r.cand
        p = float(scores[k]) if scores is not None else report.get("base_rate")
        recent.setdefault(r.asset, {}).setdefault(r.tf, []).append({
            "id": r.id, "kind": c.kind, "direction": c.direction, "forming": c.confirm is None,
            "t1": int(b.time[c.i]), "t2": int(b.time[c.j]), "confirmed_at": None if c.confirm is None else int(b.time[c.confirm]),
            "p1": c.p1, "p2": c.p2, "r1": c.r1, "r2": c.r2, "score": p, "oos_score": oos.get(r.id),
            "alert": bool(c.confirm is not None and p is not None and p >= report["thresholds"].get(r.tf, 2.0)),
            "outcome": None if r.y is None else ("worked" if r.y == 1 else "failed"), "you": r.user,
        })
    atomic_write_text(RECENT_PATH, json.dumps({"generated_at": report["trained_at"], "trusted": report["trusted"], "thresholds": report["thresholds"],
                                               "candidates": recent}, indent=None))


def load_model() -> dict | None:
    try:
        return json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_recent() -> dict | None:
    try:
        return json.loads(RECENT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
