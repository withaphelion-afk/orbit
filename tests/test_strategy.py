"""The strategy, backtest, journal, feedback loop and drift check."""

from dataclasses import replace

import numpy as np
import pytest

from orbit.analysis.series import PriceSeries
from orbit.backtest import drift, engine
from orbit.core.types import Asset, Decision, Direction
from orbit.features.arrays import wilder_rsi
from orbit.journal import store
from orbit.strategy import calibrate, live
from orbit.strategy import rsi_divergence as strat


def _walk(n=3000, seed=7) -> PriceSeries:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.025, n)))
    opens = np.concatenate([[close[0]], close[:-1]]) * (1 + rng.normal(0, 0.003, n))
    high = np.maximum(opens, close) * (1 + np.abs(rng.normal(0, 0.01, n)))
    low = np.minimum(opens, close) * (1 - np.abs(rng.normal(0, 0.01, n)))
    dates = np.arange(np.datetime64("2012-01-01"), np.datetime64("2012-01-01") + np.timedelta64(n, "D"), dtype="datetime64[D]")
    return PriceSeries(Asset.BTC, dates, opens, high, low, close)


def _cut(s: PriceSeries, end: int) -> PriceSeries:
    return PriceSeries(s.asset, s.dates[:end], s.open[:end], s.high[:end], s.low[:end], s.close[:end])


def _bars(o, h, l, c) -> PriceSeries:
    n = len(o)
    dates = np.arange(np.datetime64("2020-01-01"), np.datetime64("2020-01-01") + np.timedelta64(n, "D"), dtype="datetime64[D]")
    return PriceSeries(Asset.BTC, dates, *(np.array(x, dtype=float) for x in (o, h, l, c)))


@pytest.fixture
def journal_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "JOURNAL_DIR", tmp_path)
    monkeypatch.setattr(store, "PATH", tmp_path / "suggestions.json")
    monkeypatch.setattr(store, "BACKUPS", tmp_path / "backups")
    monkeypatch.setattr(calibrate, "PATH", tmp_path / "calibration.json")
    return tmp_path


# ---------------------------------------------------------------- RSI + signals


def test_wilder_rsi_extremes_and_balance():
    assert wilder_rsi(np.arange(1, 60, dtype=float))[-1] == 100.0
    zigzag = 100 + np.tile([1.0, -1.0], 60)
    assert abs(wilder_rsi(zigzag)[-1] - 50) < 3
    assert np.isnan(wilder_rsi(zigzag)[:14]).all()


def test_divergences_follow_the_rule():
    series = _walk()
    sigs = strat.find_signals(series)
    assert len(sigs) > 20
    for s in sigs:
        assert strat.MIN_BARS_BETWEEN <= s.bars_between <= strat.MAX_BARS_BETWEEN
        assert s.signal_index == s.second_pivot + strat.PIVOT_RIGHT
        if s.direction == Direction.LONG:
            assert s.price_second < s.price_first and s.rsi_second > s.rsi_first and s.rsi_first < strat.BULL_RSI_ZONE
            assert s.stop < series.low[s.second_pivot]
        else:
            assert s.price_second > s.price_first and s.rsi_second < s.rsi_first and s.rsi_first > strat.BEAR_RSI_ZONE
            assert s.stop > series.high[s.second_pivot]


def test_signals_use_no_future_data():
    """Every signal is found identically when the history ends on its confirmation bar."""
    series = _walk()
    for s in strat.find_signals(series)[::5]:
        early = strat.find_signals(_cut(series, s.signal_index + 1))
        match = [e for e in early if e.signal_index == s.signal_index and e.direction == s.direction]
        assert match and match[0].first_pivot == s.first_pivot and match[0].stop == pytest.approx(s.stop)


def test_levels_refuse_an_entry_past_the_stop():
    s = strat.find_signals(_walk())[0]
    past = s.stop * (0.99 if s.direction == Direction.LONG else 1.01)
    assert strat.levels(s, past) is None
    entry = s.stop * (1.05 if s.direction == Direction.LONG else 0.95)
    stop, target = strat.levels(s, entry)
    assert abs(target - entry) == pytest.approx(strat.TARGET_R * abs(entry - stop))


# ---------------------------------------------------------------- trade walking


def test_stop_wins_when_a_bar_touches_both_levels():
    s = _bars([100, 100], [100, 111], [100, 94], [100, 100])
    assert engine.walk(s, Direction.LONG, 1, 100, 95, 110, 0.0) == (1, 95, "stop")


def test_a_gap_through_the_stop_exits_at_the_open():
    s = _bars([100, 100, 90], [100, 101, 91], [100, 99, 89], [100, 100, 90])
    k, price, why = engine.walk(s, Direction.LONG, 1, 100, 95, 110, 0.0)
    assert (k, price, why) == (2, 90, "stop")


def test_time_exit_and_still_open():
    n = strat.MAX_BARS + 5
    flat = [100.0] * n
    s = _bars(flat, [101.0] * n, [99.0] * n, flat)
    k, _, why = engine.walk(s, Direction.SHORT, 1, 100, 105, 90, 0.0)
    assert why == "time" and k == strat.MAX_BARS
    assert engine.walk(_cut(s, 10), Direction.SHORT, 1, 100, 105, 90, 0.0) is None


def test_result_in_percent_and_r():
    ret, r = engine.result(Direction.LONG, 100, 95, 110, 0.0)
    assert ret == pytest.approx(10.0) and r == pytest.approx(2.0)
    ret, r = engine.result(Direction.SHORT, 100, 105, 105, 0.001)
    assert ret == pytest.approx(-5.2) and r == pytest.approx(-1.04)


def test_backtest_holds_one_trade_at_a_time_and_enters_next_open():
    series = _walk()
    trades = engine.run(Asset.BTC, series)
    assert len(trades) > 10
    for a, b in zip(trades, trades[1:]):
        assert b.entry_date > a.exit_date
    idx = {str(d): i for i, d in enumerate(series.dates)}
    for t in trades:
        e = idx[t.entry_date]
        assert e == idx[t.signal_date] + 1 and t.entry == series.open[e]
    summary = engine.summarise(trades)
    assert summary["trades"] == sum(1 for t in trades if t.r_multiple is not None)
    assert sum(summary["exit_reasons"].values()) == summary["trades"]


# ---------------------------------------------------------------- live suggestions + journal


def _signal_at_end(series):
    s = next(s for s in strat.find_signals(series) if s.signal_index > 500)
    return s, _cut(series, s.signal_index + 1)


def test_refresh_suggests_expires_and_resolves(journal_dir):
    series = _walk()
    s, upto = _signal_at_end(series)
    assert live.refresh({Asset.BTC: upto})["new"] == 1
    assert live.refresh({Asset.BTC: upto})["new"] == 0  # same signal, not duplicated
    rec = store.load()[0]
    assert rec.status == "pending" and rec.suggestion.direction == s.direction
    assert rec.suggestion.entry_price == upto.close[-1]
    assert rec.suggestion.confidence == pytest.approx(0.4)  # nothing trained yet
    later = _cut(series, s.signal_index + 1 + strat.MAX_BARS + 2)
    counts = live.refresh({Asset.BTC: later})
    rec = store.load()[0]
    assert counts["expired"] == 1 and rec.status == "expired"
    assert rec.paper is not None and rec.paper.entry == later.open[s.signal_index + 1]


def test_decisions_are_logged_once(journal_dir):
    series = _walk()
    _, upto = _signal_at_end(series)
    live.refresh({Asset.BTC: upto})
    rec = store.load()[0]
    e = rec.suggestion.entry_price
    lv = (e, e * 0.9, e * 1.2) if rec.suggestion.direction == Direction.LONG else (e, e * 1.1, e * 0.8)
    out = live.decide(rec.id, Decision.MODIFIED, "tighter", *lv)
    assert (out.acted_entry, out.acted_stop, out.acted_target) == lv
    with pytest.raises(ValueError):
        live.decide(rec.id, Decision.TAKEN, "", None, None, None)
    with pytest.raises(KeyError):
        live.decide("nope", Decision.TAKEN, "", None, None, None)
    entry = store.load()[0].journal_entry()
    assert entry.decision == Decision.MODIFIED and entry.suggestion.stop_loss == lv[1] and entry.outcome_pnl is None
    assert list((journal_dir / "backups").iterdir())


def test_decision_endpoint_and_journal(journal_dir):
    from fastapi.testclient import TestClient

    from orbit.api.app import create_app

    series = _walk()
    _, upto = _signal_at_end(series)
    live.refresh({Asset.BTC: upto})
    sid = store.load()[0].id
    c = TestClient(create_app(live=False))
    assert [v["id"] for v in c.get("/api/suggestions").json()] == [sid]
    assert c.post(f"/api/suggestions/{sid}/decision", json={"decision": "MODIFIED", "notes": ""}).status_code == 422
    r = c.post(f"/api/suggestions/{sid}/decision", json={"decision": "SKIPPED", "notes": "not convinced"})
    assert r.status_code == 200 and r.json()["entry"]["decision"] == "SKIPPED"
    assert c.post(f"/api/suggestions/{sid}/decision", json={"decision": "TAKEN", "notes": ""}).status_code == 409
    assert c.get("/api/suggestions").json() == []
    assert [row["entry"]["notes"] for row in c.get("/api/journal").json()] == ["not convinced"]


# ---------------------------------------------------------------- feedback loop + drift


def _fake_trades(n, seed, informative):
    rng = np.random.default_rng(seed)
    base = engine.run(Asset.BTC, _walk())[0]
    out = []
    for k in range(n):
        diff = float(rng.uniform(1, 20))
        win = rng.random() < (0.15 + 0.035 * diff if informative else 0.4)
        out.append(replace(base, signal_date=f"{2012 + k * 12 // n}-06-01", rsi_difference=diff, rsi_second=float(rng.uniform(20, 80)),
                           price_change=float(rng.normal(0, 0.05)), bars_between=int(rng.integers(5, 60)), atr_pct=float(rng.uniform(0.01, 0.06)),
                           volatility_pct=float(rng.random()), trend_aligned=float(rng.choice([-1, 0, 1])), r_multiple=1.0 if win else -1.0))
    return out


def test_confidence_is_the_plain_win_rate_without_skill(journal_dir, monkeypatch):
    monkeypatch.setattr(calibrate, "load_trades", lambda: _fake_trades(600, 1, informative=False))
    rep = calibrate.train()
    assert rep["skill"] is False
    feats = {"rsi_first": 30, "rsi_second": 35, "rsi_difference": 19, "price_change": -0.05, "bars_between": 20,
             "atr_pct": 0.03, "volatility_pct": 0.5, "trend_aligned": 1}
    assert calibrate.confidence(feats, "LONG") == pytest.approx(rep["base_win_rate"])


def test_confidence_follows_the_model_when_it_has_skill(journal_dir, monkeypatch):
    monkeypatch.setattr(calibrate, "load_trades", lambda: _fake_trades(1500, 2, informative=True))
    rep = calibrate.train()
    assert rep["skill"] is True and rep["weights"][0]["feature"] == "rsi_difference"
    feats = {"rsi_first": 30, "rsi_second": 35, "rsi_difference": 19, "price_change": -0.05, "bars_between": 20,
             "atr_pct": 0.03, "volatility_pct": 0.5, "trend_aligned": 1}
    strong = calibrate.confidence(feats, "LONG")
    weak = calibrate.confidence({**feats, "rsi_difference": 2}, "LONG")
    assert strong > rep["base_win_rate"] > weak


def test_drift_flags_a_live_win_rate_far_below_the_backtest(journal_dir, monkeypatch):
    monkeypatch.setattr(drift, "load_backtest", lambda: {"pooled": {"trades": 200, "win_rate": 0.5, "avg_r": 0.2, "std_r": 1.2, "max_drawdown_r": -8}})
    base = store.SuggestionRecord.model_validate_json(_one_record_json())
    losers = [base.model_copy(update={"id": f"x{k}", "paper": base.paper.model_copy(update={"r_multiple": -1.0 if k < 18 else 1.0})}) for k in range(20)]
    store.save(losers)
    rep = drift.report()
    assert rep["live_trades"] == 20 and rep["live_win_rate"] == pytest.approx(0.1)
    assert rep["z_score"] < -2 and rep["status"] == "DRIFT"
    assert rep["curve"][-1]["live"] == pytest.approx(-16.0)
    store.save(losers[:5])
    assert drift.report()["status"] == "OK"  # too few trades to judge


def _one_record_json() -> str:
    return """{"id": "BTC-2026-01-01-LONG", "created_at": "2026-01-01T00:05:00Z", "signal_date": "2026-01-01", "risk_reward": 2.0,
      "suggestion": {"asset": "BTC", "timestamp": "2026-01-01T00:00:00Z", "direction": "LONG", "confidence": 0.4, "entry_price": 100,
                     "stop_loss": 95, "take_profit": 110, "signals": []},
      "features": {}, "status": "expired",
      "paper": {"entry_date": "2026-01-02", "entry": 100, "exit_date": "2026-01-10", "exit_price": 95, "reason": "stop", "return_pct": -5.2, "r_multiple": -1.0}}"""


# ---------------------------------------------------------------- the Vedic model's machinery


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


def test_walk_forward_credits_a_planted_feature_and_not_noise():
    from orbit.analysis.model import walk_forward
    from orbit.analysis.outcomes import BIG_UP, label_outcomes

    series = _walk(4000, seed=3)
    codes = label_outcomes(series, 5).codes
    rng = np.random.default_rng(1)
    tech = rng.normal(size=(len(series), 3))
    y = (codes == BIG_UP).astype(float)
    planted = np.column_stack([y, rng.random(len(series)) < 0.3]).astype(float)
    noise = (rng.random((len(series), 2)) < 0.3).astype(float)

    def skill(vedic):
        idx, p, clim = walk_forward(series, tech, vedic, codes, BIG_UP, 5)
        from orbit.analysis.model import log_loss

        return 1 - log_loss(y[idx], p) / log_loss(y[idx], clim)

    assert skill(planted) > 0.5
    assert skill(noise) < 0.01
