"""The feedback loop: learn which divergences actually work, and set confidence from that.

A small logistic model estimates P(win), the chance a divergence trade ends
with a positive result, from what was known at the signal bar: how big the
RSI divergence was, where RSI stood, how far price moved between the swings,
how far apart they were, volatility, whether the trend agreed, and long vs
short. It learns from every backtest trade plus every live suggestion that
has played out (paper outcomes, weighted LIVE_WEIGHT x, since they are the
most recent evidence), and it is retrained on every analysis run, so it keeps
adjusting as outcomes arrive. That P(win) is each suggestion's confidence.

It is also checked out-of-sample (walk-forward by year on the backtest
trades): the calibration table shows whether "60%" really wins about 60%.
The model's number is used as confidence only if it beat the plain win rate
out-of-sample (lower Brier score). Until it does, every suggestion gets the
plain win rate, because a confident-looking number with no skill behind it
would be worse than an honest flat one.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

from orbit.config.settings import DATA_DIR
from orbit.analysis.model import _sigmoid, auc, log_loss
from orbit.backtest.engine import Trade, load_trades
from orbit.journal import store

PATH = DATA_DIR / "strategy" / "calibration.json"
FEATURES = ["rsi_difference", "rsi_level", "price_change_abs", "bars_between", "atr_pct", "volatility_pct", "trend_aligned", "is_long"]
LIVE_WEIGHT = 3.0
LAMBDA = 5.0
MIN_TRAIN = 40


def row(features: dict, direction: str) -> list[float]:
    return [
        features["rsi_difference"],
        features["rsi_second"] / 100,
        abs(features["price_change"]),
        features["bars_between"],
        features["atr_pct"],
        features["volatility_pct"],
        features["trend_aligned"],
        1.0 if direction == "LONG" else 0.0,
    ]


def _fit(X: np.ndarray, y: np.ndarray, w: np.ndarray) -> dict:
    mu, sd = X.mean(axis=0), X.std(axis=0) + 1e-9
    Z = np.hstack([np.ones((len(X), 1)), (X - mu) / sd])
    coef = np.zeros(Z.shape[1])
    base = np.clip(np.average(y, weights=w), 1e-3, 1 - 1e-3)
    coef[0] = np.log(base / (1 - base))
    pen = np.full(len(coef), LAMBDA)
    pen[0] = 0
    for _ in range(12):
        p = _sigmoid(Z @ coef)
        grad = Z.T @ (w * (p - y)) + pen * coef
        H = (Z * (w * p * (1 - p))[:, None]).T @ Z + np.diag(pen + 1e-9)
        coef -= np.linalg.solve(H, grad)
    return {"mu": mu.tolist(), "sd": sd.tolist(), "coef": coef.tolist()}


def predict(model: dict, features: dict, direction: str) -> float:
    x = (np.array(row(features, direction)) - np.array(model["mu"])) / np.array(model["sd"])
    return float(_sigmoid(model["coef"][0] + x @ np.array(model["coef"][1:])))


def _dataset(trades: list[Trade], records: list[store.SuggestionRecord]):
    X, y, w, years = [], [], [], []
    for t in trades:
        if t.r_multiple is None:
            continue
        X.append(row(t.__dict__, t.direction))
        y.append(1.0 if t.r_multiple > 0 else 0.0)
        w.append(1.0)
        years.append(int(t.signal_date[:4]))
    for r in records:
        if r.paper is None:
            continue
        X.append(row(r.features, r.suggestion.direction.value))
        y.append(1.0 if r.paper.r_multiple > 0 else 0.0)
        w.append(LIVE_WEIGHT)
        years.append(int(r.signal_date[:4]))
    return np.array(X), np.array(y), np.array(w), np.array(years)


def train() -> dict:
    trades = load_trades()
    records = store.load()
    X, y, w, years = _dataset(trades, records)
    report: dict = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "features": FEATURES,
        "n_backtest": int(sum(1 for t in trades if t.r_multiple is not None)),
        "n_live": int(sum(1 for r in records if r.paper is not None)),
        "base_win_rate": float(np.average(y, weights=w)) if len(y) else None,
        "model": None,
        "out_of_sample": None,
        "skill": False,
    }
    if len(y) < MIN_TRAIN:
        report["note"] = f"Only {len(y)} finished trades; confidence falls back to the plain win rate until there are {MIN_TRAIN}."
    else:
        report["model"] = _fit(X, y, w)
        # Walk-forward check: train on earlier years, predict the next one.
        preds, truth, clim = [], [], []
        for yr in np.unique(years):
            tr, te = years < yr, years == yr
            if tr.sum() < MIN_TRAIN or te.sum() == 0:
                continue
            m = _fit(X[tr], y[tr], w[tr])
            Z = (X[te] - np.array(m["mu"])) / np.array(m["sd"])
            preds.append(_sigmoid(m["coef"][0] + Z @ np.array(m["coef"][1:])))
            truth.append(y[te])
            clim.append(np.full(te.sum(), np.average(y[tr], weights=w[tr])))
        if preds:
            p, t, c = np.concatenate(preds), np.concatenate(truth), np.concatenate(clim)
            edges = np.quantile(p, [0, 0.2, 0.4, 0.6, 0.8, 1.0])
            buckets = []
            for lo, hi in zip(edges[:-1], edges[1:]):
                m = (p >= lo) & (p <= hi)
                if m.sum():
                    buckets.append({"predicted": float(p[m].mean()), "actual": float(t[m].mean()), "n": int(m.sum())})
            report["out_of_sample"] = {
                "n": int(len(t)),
                "brier": float(np.mean((p - t) ** 2)),
                "brier_base_rate": float(np.mean((c - t) ** 2)),
                "log_loss": log_loss(t, p),
                "log_loss_base_rate": log_loss(t, c),
                "auc": auc(t, p),
                "buckets": buckets,
            }
            report["skill"] = report["out_of_sample"]["brier"] < report["out_of_sample"]["brier_base_rate"]
        coef = report["model"]["coef"][1:]
        report["weights"] = sorted(({"feature": f, "weight": float(c)} for f, c in zip(FEATURES, coef)), key=lambda d: -abs(d["weight"]))
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def load() -> dict | None:
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else None


def confidence(features: dict, direction: str) -> float:
    rep = load()
    if not rep:
        return 0.4
    if rep.get("model") and rep.get("skill"):
        return predict(rep["model"], features, direction)
    return float(rep.get("base_win_rate") or 0.4)
