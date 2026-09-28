"""A trained model: does knowing the Vedic sky improve a forecast of what price does next?

For each asset and horizon (5 and 20 daily bars), three regularised logistic
regressions predict whether the next H bars will be a BIG_UP, BIG_DOWN or
SIDEWAYS stretch (the same labels as the playbook):

    TECH            price-only features (returns, volatility, trend, regime, RSI)
    TECH+VEDIC      the same plus every Vedic state (orbit/vedic/states.py)
    TECH+CONTROL    the same plus the Vedic states slid to the wrong dates

Walk-forward, never in-sample: the model is refit every RETRAIN_YEARS on all
data before that period (minus a gap of H bars so no training label overlaps
the test period) and scored only on the period it hasn't seen. Scores are
out-of-sample log-loss, Brier score and AUC, and "skill" = improvement in
log-loss over simply predicting the historical base rate.

The Vedic features only earn credit ("adds skill") if TECH+VEDIC beats TECH,
beats every TECH+CONTROL run, beats simply guessing the base rate (skill > 0),
and does better than TECH in most test years. The control has exactly the same
features with the same persistence and rhythm, just misaligned with prices, so
any "skill" it shows is what fitting hundreds of features buys by chance.

Six targets are checked per asset (24 across the four), so one or two can pass
by chance alone; a pass is something to watch across later runs, not proof.

The fitted final model (all data) also gives today's probabilities.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import numpy as np

from orbit.config.settings import DATA_DIR
from orbit.core.types import Asset
from orbit.features.arrays import rolling_mean
from orbit.features.regime import trend_values
from orbit.features.technical import technical_arrays
from orbit.analysis.outcomes import BIG_DOWN, BIG_UP, SIDEWAYS, UNDEFINED, label_outcomes
from orbit.analysis.series import PriceSeries
from orbit.vedic.states import States, on_dates

MODEL_DIR = DATA_DIR / "analysis" / "model"
HORIZONS = [5, 20]
TARGETS = {BIG_UP: "big_up", BIG_DOWN: "big_down", SIDEWAYS: "sideways"}
RETRAIN_YEARS = 2
MIN_TRAIN_YEARS = 3
LAMBDAS = [1.0, 10.0, 100.0]  # ridge strengths tried on an inner validation split
MIN_PREVALENCE = 0.01  # Vedic states true on <1% (or >99%) of training days are dropped
CONTROL_SHIFTS_DAYS = [739, 1531]  # ~2 and ~4.2 years: well away from any yearly rhythm
NEWTON_STEPS = 8


# ---------------------------------------------------------------- features


def _rsi(close: np.ndarray, n: int = 14) -> np.ndarray:
    d = np.diff(close, prepend=close[0])
    up, down = rolling_mean(np.maximum(d, 0), n), rolling_mean(np.maximum(-d, 0), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100 - 100 / (1 + up / np.where(down == 0, np.nan, down))


def tech_features(series: PriceSeries) -> tuple[np.ndarray, list[str]]:
    c = series.close
    t = technical_arrays(c)
    ret5 = np.full(len(c), np.nan)
    ret20 = np.full(len(c), np.nan)
    ret5[5:] = c[5:] / c[:-5] - 1
    ret20[20:] = c[20:] / c[:-20] - 1
    vol = t["volatility_20d"]
    # The rolling mean is built on cumulative sums, so fill the leading warm-up gap
    # with the first real value (no future data) rather than let NaN spread.
    first = int(np.flatnonzero(~np.isnan(vol))[0]) if np.any(~np.isnan(vol)) else 0
    vol_filled = np.where(np.isnan(vol), vol[first], vol)
    vol_ratio = np.where(np.isnan(vol), np.nan, vol / rolling_mean(vol_filled, 250))
    cols = {
        "return_1d": t["return_1d"],
        "return_5d": ret5,
        "return_20d": ret20,
        "volatility_20d": vol,
        "volatility_vs_1y": vol_ratio,
        "close_vs_sma50": t["close_vs_sma50"],
        "close_vs_sma200": t["close_vs_sma200"],
        "trend": trend_values(c),
        "rsi_14": _rsi(c) / 100,
    }
    return np.column_stack(list(cols.values())), list(cols.keys())


def vedic_features(series: PriceSeries, states: States) -> tuple[np.ndarray, list[str], list[str]]:
    masks = on_dates(states, series.dates, include_moon=True)
    ids = sorted(masks)
    return np.column_stack([masks[i][1] for i in ids]).astype(float), ids, [masks[i][0] for i in ids]


# ---------------------------------------------------------------- model


def _sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def fit_logistic(X: np.ndarray, y: np.ndarray, lam: float) -> np.ndarray:
    """Ridge logistic regression by Newton's method; column 0 is the (unpenalised) intercept."""
    n, p = X.shape
    w = np.zeros(p)
    base = np.clip(y.mean(), 1e-4, 1 - 1e-4)
    w[0] = math.log(base / (1 - base))
    penalty = np.full(p, lam)
    penalty[0] = 0.0
    for _ in range(NEWTON_STEPS):
        prob = _sigmoid(X @ w)
        grad = X.T @ (prob - y) + penalty * w
        H = (X * (prob * (1 - prob))[:, None]).T @ X + np.diag(penalty + 1e-9)
        w -= np.linalg.solve(H, grad)
    return w


def log_loss(y, p) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def auc(y, p) -> float | None:
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return None
    ranks = np.argsort(np.argsort(np.concatenate([pos, neg]))) + 1
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


class Design:
    """Standardises technical columns on training data only, keeps Vedic columns that vary."""

    def __init__(self, tech: np.ndarray, vedic: np.ndarray | None, train: np.ndarray):
        self.mu = np.nanmean(tech[train], axis=0)
        self.sd = np.nanstd(tech[train], axis=0) + 1e-12
        if vedic is not None:
            prev = vedic[train].mean(axis=0)
            self.keep = np.flatnonzero((prev >= MIN_PREVALENCE) & (prev <= 1 - MIN_PREVALENCE))
        else:
            self.keep = np.array([], dtype=int)

    def __call__(self, tech: np.ndarray, vedic: np.ndarray | None, rows) -> np.ndarray:
        t = np.nan_to_num((tech[rows] - self.mu) / self.sd)
        parts = [np.ones((len(t), 1)), t]
        if vedic is not None and len(self.keep):
            parts.append(vedic[rows][:, self.keep])
        return np.hstack(parts)


def _choose_lambda(tech, vedic, y, train_idx) -> float:
    """Pick the ridge strength on the last 20% of the training period."""
    cut = train_idx[int(len(train_idx) * 0.8)]
    inner_tr, inner_va = train_idx[train_idx < cut], train_idx[train_idx >= cut]
    if len(inner_va) < 50 or y[inner_tr].sum() < 10:
        return LAMBDAS[1]
    d = Design(tech, vedic, inner_tr)
    scores = []
    for lam in LAMBDAS:
        w = fit_logistic(d(tech, vedic, inner_tr), y[inner_tr], lam)
        scores.append(log_loss(y[inner_va], _sigmoid(d(tech, vedic, inner_va) @ w)))
    return LAMBDAS[int(np.argmin(scores))]


def walk_forward(series: PriceSeries, tech: np.ndarray, vedic: np.ndarray | None, codes: np.ndarray, target: int, horizon: int):
    """Out-of-sample predictions: (test indices, probabilities, climatology probabilities)."""
    years = series.dates.astype("datetime64[Y]").astype(int) + 1970
    defined = (codes != UNDEFINED) & ~np.isnan(tech).any(axis=1)
    y = (codes == target).astype(float)
    first = years[defined].min() + MIN_TRAIN_YEARS
    out_idx, out_p, out_clim = [], [], []
    for start in range(int(first), int(years.max()) + 1, RETRAIN_YEARS):
        test = np.flatnonzero(defined & (years >= start) & (years < start + RETRAIN_YEARS))
        if not len(test):
            continue
        train = np.flatnonzero(defined & (np.arange(len(y)) < test[0] - horizon))
        if y[train].sum() < 20:
            continue
        lam = _choose_lambda(tech, vedic, y, train)
        d = Design(tech, vedic, train)
        w = fit_logistic(d(tech, vedic, train), y[train], lam)
        out_idx.append(test)
        out_p.append(_sigmoid(d(tech, vedic, test) @ w))
        out_clim.append(np.full(len(test), y[train].mean()))
    if not out_idx:
        return None
    return np.concatenate(out_idx), np.concatenate(out_p), np.concatenate(out_clim)


def _score(y, p, clim) -> dict:
    ll, ll0 = log_loss(y, p), log_loss(y, clim)
    return {
        "n": int(len(y)),
        "log_loss": ll,
        "climatology_log_loss": ll0,
        "skill": 1 - ll / ll0,
        "brier": float(np.mean((p - y) ** 2)),
        "auc": auc(y, p),
    }


def _yearly_skill(series, idx, y, p, clim) -> dict[str, float]:
    years = series.dates[idx].astype("datetime64[Y]").astype(int) + 1970
    return {str(int(yr)): 1 - log_loss(y[years == yr], p[years == yr]) / log_loss(y[years == yr], clim[years == yr]) for yr in np.unique(years)}


def evaluate(asset: Asset, series: PriceSeries, states: States) -> dict:
    tech, tech_names = tech_features(series)
    vedic, vedic_ids, vedic_desc = vedic_features(series, states)
    controls = [np.roll(vedic, s, axis=0) for s in CONTROL_SHIFTS_DAYS if s < len(vedic) // 2]
    results = {}
    forecast = {}
    for h in HORIZONS:
        codes = label_outcomes(series, h).codes
        for target, name in TARGETS.items():
            key = f"{name}_{h}d"
            runs = {"TECH": walk_forward(series, tech, None, codes, target, h), "TECH+VEDIC": walk_forward(series, tech, vedic, codes, target, h)}
            for k, ctrl in enumerate(controls):
                runs[f"TECH+CONTROL{k + 1}"] = walk_forward(series, tech, ctrl, codes, target, h)
            if runs["TECH"] is None or runs["TECH+VEDIC"] is None:
                continue
            idx = runs["TECH"][0]
            y = (codes[idx] == target).astype(float)
            scores = {m: _score(y, r[1], r[2]) for m, r in runs.items() if r is not None and len(r[0]) == len(idx)}
            gain = scores["TECH+VEDIC"]["log_loss"]
            base = scores["TECH"]["log_loss"]
            control_gains = [base - s["log_loss"] for m, s in scores.items() if m.startswith("TECH+CONTROL")]
            vedic_gain = base - gain
            yearly_v = _yearly_skill(series, idx, y, runs["TECH+VEDIC"][1], runs["TECH+VEDIC"][2])
            yearly_t = _yearly_skill(series, idx, y, runs["TECH"][1], runs["TECH"][2])
            years_better = sum(1 for yr in yearly_v if yearly_v[yr] > yearly_t[yr])
            beats_controls = bool(control_gains) and vedic_gain > max(control_gains)
            verdict = (
                "adds skill"
                if vedic_gain > 0 and beats_controls and scores["TECH+VEDIC"]["skill"] > 0 and years_better > len(yearly_v) / 2
                else "no added skill" if vedic_gain <= 0 or not beats_controls
                else "unclear"
            )
            results[key] = {
                "target": name,
                "horizon_days": h,
                "base_rate": float(y.mean()),
                "scores": scores,
                "vedic_log_loss_gain": vedic_gain,
                "control_log_loss_gains": control_gains,
                "years_vedic_better": years_better,
                "years": len(yearly_v),
                "yearly_skill": {"TECH": yearly_t, "TECH+VEDIC": yearly_v},
                "verdict": verdict,
            }

            # Final fit on everything with a known outcome, for today's forecast and the feature weights.
            defined = (codes != UNDEFINED) & ~np.isnan(tech).any(axis=1)
            train = np.flatnonzero(defined)
            yy = (codes == target).astype(float)
            last = np.array([len(series) - 1])
            for model, v in (("TECH", None), ("TECH+VEDIC", vedic)):
                d = Design(tech, v, train)
                w = fit_logistic(d(tech, v, train), yy[train], _choose_lambda(tech, v, yy, train))
                forecast.setdefault(key, {})[model] = float(_sigmoid(d(tech, v, last) @ w)[0])
                if model == "TECH+VEDIC":
                    weights = w[1 + len(tech_names):]
                    top = np.argsort(-np.abs(weights))[:8]
                    results[key]["top_vedic_features"] = [
                        {"state": vedic_ids[d.keep[i]], "description": vedic_desc[d.keep[i]], "weight": float(weights[i])} for i in top
                    ]
            forecast[key]["base_rate"] = float(yy[train].mean())
    added = [k for k, r in results.items() if r["verdict"] == "adds skill"]
    report = {
        "asset": asset.value,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": str(series.dates[-1]),
        "method": "walk-forward ridge logistic regression; Vedic credited only if it beats price-only and misaligned-Vedic controls",
        "tech_features": tech_names,
        "vedic_features": len(vedic_ids),
        "retrain_years": RETRAIN_YEARS,
        "results": results,
        "forecast": forecast,
        "summary": (
            f"Vedic features add out-of-sample skill for {', '.join(added)} ({len(added)} of {len(results)} targets). "
            "With this many targets checked, one or two can pass by chance: watch whether it holds on later runs."
            if added
            else f"Vedic features add no out-of-sample skill beyond price alone for any of the {len(results)} targets."
        ),
    }
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    (MODEL_DIR / f"{asset.value}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def load(asset: Asset) -> dict | None:
    path = MODEL_DIR / f"{asset.value}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
