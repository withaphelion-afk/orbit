"""The divergence system: detection, labels, the learning model, suggestions, backtest, journal and drift."""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from orbit.backtest import drift, engine
from orbit.core.types import Asset, Decision
from orbit.journal import store
from orbit.strategy import bars as bars_mod
from orbit.strategy import divergence as det
from orbit.strategy import divergence_model as dm
from orbit.strategy import live

CASES = json.loads((Path(__file__).parent / "fixtures" / "divergence_cases.json").read_text(encoding="utf-8"))


def _walk(n=1500, seed=7, timeframe="1d") -> bars_mod.Bars:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.025, n)))
    opens = np.concatenate([[close[0]], close[:-1]]) * (1 + rng.normal(0, 0.003, n))
    high = np.maximum(opens, close) * (1 + np.abs(rng.normal(0, 0.01, n)))
    low = np.minimum(opens, close) * (1 - np.abs(rng.normal(0, 0.01, n)))
    step = bars_mod.SECONDS[timeframe]
    t = (1_600_000_000 // step) * step + np.arange(n, dtype=np.int64) * step
    return bars_mod.Bars(Asset.BTC, timeframe, t, opens, high, low, close, rng.uniform(1, 2, n))


@pytest.fixture
def journal_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "JOURNAL_DIR", tmp_path)
    monkeypatch.setattr(store, "PATH", tmp_path / "suggestions.json")
    monkeypatch.setattr(store, "BACKUPS", tmp_path / "backups")
    monkeypatch.setattr(dm, "LABELS_PATH", tmp_path / "divergence_labels.json")
    return tmp_path


# ---------------------------------------------------------------- detection (shared with web/src/lib/divergence.ts)


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_detection_matches_the_shared_cases(case):
    """The same file is checked by the TypeScript suite: both implementations must agree."""
    r = det.rsi(case["close"])
    assert all((x is None and math.isnan(y)) or (x is not None and y == pytest.approx(x, abs=1e-9)) for x, y in zip(case["rsi"], r))
    lows, highs = det.swings(np.array(case["high"]), np.array(case["low"]))
    assert (lows, highs) == (case["swings"]["lows"], case["swings"]["highs"])
    got = [c.as_dict() for c in det.find(case["high"], case["low"], case["close"])]
    assert len(got) == len(case["expected"])
    for g, e in zip(got, case["expected"]):
        assert {k: g[k] for k in ("kind", "direction", "i", "j", "confirm", "s1", "s2")} == {k: e[k] for k in ("kind", "direction", "i", "j", "confirm", "s1", "s2")}
        assert g["r1"] == pytest.approx(e["r1"], abs=1e-9) and g["r2"] == pytest.approx(e["r2"], abs=1e-9)


def test_rsi_extremes():
    assert det.rsi(np.arange(1, 60, dtype=float))[-1] == 100.0
    assert abs(det.rsi(100 + np.tile([1.0, -1.0], 60))[-1] - 50) < 3
    assert np.isnan(det.rsi(np.arange(10.0))).all()


def test_every_candidate_follows_its_rule_and_uses_no_future_data():
    b = _walk(800)
    found = det.find(b.high, b.low, b.close)
    assert {c.kind for c in found} == {"regular", "hidden"} and {c.direction for c in found} == {"LONG", "SHORT"}
    for c in found:
        assert det.MIN_GAP <= c.j - c.i <= det.MAX_GAP
        if c.direction == "LONG":
            assert (c.p2 < c.p1 and c.r2 > c.r1) if c.kind == "regular" else (c.p2 > c.p1 and c.r2 < c.r1)
        else:
            assert (c.p2 > c.p1 and c.r2 < c.r1) if c.kind == "regular" else (c.p2 < c.p1 and c.r2 > c.r1)
    for c in [c for c in found if c.confirm is not None][::25]:
        early = det.find(b.high[: c.confirm + 1], b.low[: c.confirm + 1], b.close[: c.confirm + 1])
        same = [e for e in early if (e.i, e.j, e.direction) == (c.i, c.j, c.direction)]
        assert same and same[0].confirm == c.confirm and (same[0].s1, same[0].s2) == (c.s1, c.s2)


def test_a_forming_divergence_becomes_confirmed_or_disappears():
    b = _walk(800, seed=11)
    for end in range(300, 800, 37):
        for c in [c for c in det.find(b.high[:end], b.low[:end], b.close[:end]) if c.forming]:
            assert c.j >= end - det.RIGHT
            later = det.find(b.high[: c.j + det.RIGHT + 1], b.low[: c.j + det.RIGHT + 1], b.close[: c.j + det.RIGHT + 1], include_forming=False)
            assert all(x.confirm == c.j + det.RIGHT for x in later if (x.i, x.j, x.direction) == (c.i, c.j, c.direction))


# ---------------------------------------------------------------- bars


def test_4h_and_1w_bars_aggregate_and_drop_the_open_bar():
    b = _walk(48, timeframe="1h")
    four = bars_mod.aggregate(b, "4h")
    assert len(four) in (12, 13) and (four.time % (4 * 3600) == 0).all()
    k = 1
    s = np.flatnonzero((b.time >= four.time[k]) & (b.time < four.time[k] + 4 * 3600))
    assert four.high[k] == b.high[s].max() and four.low[k] == b.low[s].min() and four.close[k] == b.close[s[-1]]
    done = bars_mod.completed(four, now=float(four.time[-1] + 3600))
    assert len(done) == len(four) - 1
    week = bars_mod.aggregate(_walk(30, timeframe="1d"), "1w")
    assert ((week.time - bars_mod.WEEK_ORIGIN) % (7 * 86400) == 0).all()


# ---------------------------------------------------------------- labels and the model


def test_labels_count_the_right_move_first():
    b = _walk(10, timeframe="1d")
    b.close[:] = 100.0
    b.open[:] = 100.0
    b.high[:] = 100.5
    b.low[:] = 99.5
    ctx = dm.Context(b, *(np.zeros(10),) * 3, move=0.05, regime=np.zeros(10))
    c = det.Candidate("regular", "LONG", 0, 3, 5, 1, 1, 30, 35, 1, 1)
    b.high[7] = 106.0
    assert dm.label(c, ctx) == 1
    b.low[6] = 94.0
    assert dm.label(c, ctx) == 0  # the wrong way came first
    assert dm.label(det.Candidate("regular", "LONG", 0, 3, None, 1, 1, 30, 35, 1, 1), ctx) is None


def _rows(n_assets_rows=400, planted=True, seed=0):
    rng = np.random.default_rng(seed)
    b = _walk(50)
    ctx = dm.Context(b, *(np.zeros(50),) * 3, move=0.05, regime=np.zeros(50))
    rows = []
    for k in range(n_assets_rows):
        x = rng.normal(size=len(dm.FEATURES)).tolist()
        p = 1 / (1 + math.exp(-(2 * x[0] - 1))) if planted else 0.25
        y = int(rng.random() < p)
        c = det.Candidate("regular", "LONG", 1, 8, 10, 1, 1, 30, 35, 1, 1)
        rows.append(dm.Row(f"BTC|1d|{k}|{k + 1}|LONG", "BTC", "1d", 1_600_000_000 + k * 86400, x, y, None, c, ctx))
    return rows


def test_the_model_is_trusted_only_when_it_beats_the_base_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "STRATEGY_DIR", tmp_path)
    monkeypatch.setattr(dm, "MODEL_PATH", tmp_path / "m.json")
    monkeypatch.setattr(dm, "RECENT_PATH", tmp_path / "r.json")
    assert dm.train(_rows(1500, planted=True))["trusted"] is True
    noise = dm.train(_rows(1500, planted=False, seed=1))
    assert noise["trusted"] is False and noise["base_rate"] == pytest.approx(0.25, abs=0.05)
    saved = json.loads((tmp_path / "m.json").read_text())
    assert "oos_scores" not in saved and saved["thresholds"]["1d"] > 0


def test_your_label_overrides_the_market_and_counts_more(journal_dir):
    rows = _rows(10)
    rows[0].user, rows[0].y = "real", 0
    assert dm._target(rows[0]) == (1.0, float(dm.DIVERGENCE_USER_WEIGHT))
    assert dm._target(rows[1]) == (float(rows[1].y), 1.0)
    dm.add_label("BTC", "4h", 1, 2, "LONG", "real")
    dm.add_label("BTC", "4h", 1, 2, "LONG", "not")  # a later label replaces the earlier one
    assert [x["verdict"] for x in dm.load_labels()] == ["not"]
    with pytest.raises(ValueError):
        dm.add_label("BTC", "4h", 1, 2, "LONG", "maybe")


# ---------------------------------------------------------------- trades


def test_stop_wins_when_a_bar_touches_both_levels_and_gaps_exit_at_the_open():
    b = _walk(5)
    b.open[:] = [100, 100, 90, 100, 100]
    b.high[:] = [100, 111, 91, 100, 100]
    b.low[:] = [100, 94, 89, 100, 100]
    assert engine.walk(b, "LONG", 1, 100, 95, 110, 30) == (1, 95, "stop")
    assert engine.walk(b, "LONG", 2, 100, 95, 110, 30)[2] == "stop"


def test_levels_use_the_swing_extreme_and_2r():
    assert engine.levels("LONG", 100, 95) == (95, 110)
    assert engine.levels("SHORT", 100, 104) == (104, 92)
    assert engine.levels("LONG", 100, 101) is None


def test_backtest_enters_next_open_one_trade_at_a_time():
    b = _walk(1500)
    found = [c for c in det.find(b.high, b.low, b.close) if c.confirm is not None]
    cands = [{"direction": c.direction, "kind": c.kind, "confirmed_at": int(b.time[c.confirm]), "p2": c.p2, "oos_score": 0.9} for c in found]
    trades = engine.run(Asset.BTC, "1d", b, cands, threshold=0.5)
    assert len(trades) > 10
    for a, c in zip(trades, trades[1:]):
        assert c.entry_date > a.exit_date
    assert engine.run(Asset.BTC, "1d", b, cands, threshold=0.95) == []  # below the threshold: never traded


# ---------------------------------------------------------------- live suggestions, journal, drift


def _recent_with_alert(b, tf="1d"):
    found = [c for c in det.find(b.high, b.low, b.close) if c.confirm == len(b) - 1]
    assert found, "need a divergence confirming on the last bar"
    c = found[0]
    return {"trusted": False, "candidates": {"BTC": {tf: [{"id": "x", "kind": c.kind, "direction": c.direction, "alert": True, "score": 0.42,
                                                           "confirmed_at": int(b.time[c.confirm]), "p1": c.p1, "p2": c.p2, "r1": c.r1, "r2": c.r2}]}}}, c


def _bars_ending_on_a_divergence(tf="1d"):
    b = _walk(1500, timeframe=tf)
    c = next(c for c in det.find(b.high, b.low, b.close) if c.confirm and c.confirm > 600 and engine.levels(c.direction, b.close[c.confirm], c.p2))
    return b, _cut(b, c.confirm + 1)  # the full history, and the same history ending on the confirmation bar


def _cut(b, end):
    return bars_mod.Bars(b.asset, b.timeframe, b.time[:end], b.open[:end], b.high[:end], b.low[:end], b.close[:end], b.volume[:end])


def test_refresh_suggests_on_4h_and_1d_expires_in_its_own_bars_and_resolves(journal_dir):
    for tf in ("4h", "1d"):
        full, upto = _bars_ending_on_a_divergence(tf)
        recent, c = _recent_with_alert(upto, tf)
        assert live.refresh(recent, {(Asset.BTC, tf): upto})["new"] == 1
        rec = [r for r in store.load() if r.timeframe == tf][0]
        assert rec.status == "pending" and rec.suggestion.entry_price == upto.close[-1] and rec.suggestion.stop_loss == c.p2
        assert rec.suggestion.take_profit == pytest.approx(engine.levels(c.direction, upto.close[-1], c.p2)[1])
        later = _cut(full, len(upto) + 40)
        counts = live.refresh({"candidates": {}}, {(Asset.BTC, tf): later})
        rec = [r for r in store.load() if r.timeframe == tf][0]
        assert counts["expired"] == 1 and rec.status == "expired" and rec.paper is not None


def test_decisions_are_logged_once(journal_dir):
    full, upto = _bars_ending_on_a_divergence()
    recent, _ = _recent_with_alert(upto)
    live.refresh(recent, {(Asset.BTC, "1d"): upto})
    rec = store.load()[0]
    live.decide(rec.id, Decision.SKIPPED, "not convinced", None, None, None)
    with pytest.raises(ValueError):
        live.decide(rec.id, Decision.TAKEN, "", None, None, None)
    with pytest.raises(KeyError):
        live.decide("nope", Decision.TAKEN, "", None, None, None)


def test_drift_is_per_timeframe(journal_dir, monkeypatch):
    monkeypatch.setattr(drift, "load_backtest", lambda: {"timeframes": {"1d": {"pooled": {"trades": 200, "win_rate": 0.5, "avg_r": 0.2, "std_r": 1.2,
                                                                                          "max_drawdown_r": -8}}}})
    base = store.SuggestionRecord.model_validate_json(_one_record_json())
    losers = [base.model_copy(update={"id": f"x{k}", "paper": base.paper.model_copy(update={"r_multiple": -1.0 if k < 18 else 1.0})}) for k in range(20)]
    store.save(losers + [base.model_copy(update={"id": "h", "timeframe": "4h"})])
    rep = drift.report("1d")
    assert rep["live_trades"] == 20 and rep["status"] == "DRIFT" and rep["timeframe"] == "1d"
    assert drift.report("4h") is None  # no 4H backtest: nothing to compare against


def _one_record_json() -> str:
    return """{"id": "BTC-1d-2026-01-01T00:00-LONG", "created_at": "2026-01-01T00:05:00Z", "signal_date": "2026-01-01T00:00:00+00:00", "risk_reward": 2.0,
      "suggestion": {"asset": "BTC", "timestamp": "2026-01-01T00:00:00Z", "direction": "LONG", "confidence": 0.4, "entry_price": 100,
                     "stop_loss": 95, "take_profit": 110, "signals": []},
      "features": {}, "status": "expired",
      "paper": {"entry_date": "2026-01-02T00:00:00+00:00", "entry": 100, "exit_date": "2026-01-10T00:00:00+00:00", "exit_price": 95, "reason": "stop",
                "return_pct": -5.2, "r_multiple": -1.0}}"""


def test_old_records_without_a_timeframe_still_load(journal_dir):
    raw = json.loads(_one_record_json())
    raw.pop("timeframe", None)
    raw["signal_date"] = "2026-01-01"
    rec = store.SuggestionRecord.model_validate(raw)
    assert rec.timeframe == "1d"


# ---------------------------------------------------------------- the Vedic model's machinery (analysis/model.py)


def test_auc_and_logistic_fit():
    from orbit.analysis.model import auc, fit_logistic

    y = np.array([0, 0, 1, 1.0])
    assert auc(y, np.array([0.1, 0.2, 0.8, 0.9])) == 1.0
    assert auc(y, np.array([0.9, 0.8, 0.2, 0.1])) == 0.0
    rng = np.random.default_rng(0)
    x = rng.normal(size=4000)
    yy = (rng.random(4000) < 1 / (1 + np.exp(-(0.5 + 2 * x)))).astype(float)
    w = fit_logistic(np.column_stack([np.ones(4000), x]), yy, 1.0)
    assert w[0] == pytest.approx(0.5, abs=0.15) and w[1] == pytest.approx(2.0, abs=0.2)
