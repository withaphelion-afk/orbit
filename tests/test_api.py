import warnings
from datetime import datetime, timedelta, timezone

import pytest

warnings.filterwarnings("ignore", message=".*httpx.*")
from fastapi.testclient import TestClient  # noqa: E402

from orbit.api import app as app_module  # noqa: E402
from orbit.api import store  # noqa: E402
from orbit.core.types import Asset, Candle  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app_module.create_app(live=False))


def _bars(asset: Asset, days: int, start_price: float = 100.0) -> list[Candle]:
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return [
        Candle(asset=asset, timestamp=today - timedelta(days=days - 1 - i), open=start_price + i, high=start_price + i + 1,
               low=start_price + i - 1, close=start_price + i, volume=1, source="test")
        for i in range(days)
    ]


def test_empty_journal_and_no_backtest_answer_honestly(client, monkeypatch, tmp_path):
    from orbit.backtest import drift as drift_module
    from orbit.backtest import engine
    from orbit.journal import store as journal_store

    monkeypatch.setattr(journal_store, "PATH", tmp_path / "suggestions.json")
    monkeypatch.setattr(engine, "BACKTEST_DIR", tmp_path / "backtest")
    monkeypatch.setattr(drift_module, "load_backtest", lambda: None)
    assert client.get("/api/suggestions").json() == []
    assert client.get("/api/journal").json() == []
    assert client.post("/api/suggestions/abc/decision", json={"decision": "TAKEN"}).status_code == 404
    drift = client.get("/api/drift")
    assert drift.status_code == 404 and "backtest" in drift.json()["detail"]
    assert client.get("/api/backtest").status_code == 404


def test_missing_history_is_a_clear_404(client, monkeypatch):
    monkeypatch.setattr(store, "candles", lambda asset: [])
    r = client.get("/api/candles/BTC")
    assert r.status_code == 404 and "fetch_data" in r.json()["detail"]


def test_system_reports_never_run_and_components(client, monkeypatch):
    monkeypatch.setattr(app_module, "read_status", lambda: None)
    monkeypatch.setattr(store, "backtest_exists", lambda: False)
    monkeypatch.setattr(store, "candles", lambda asset: [])
    monkeypatch.setattr(store, "history_report", lambda: {})
    monkeypatch.setattr(store, "playbook_meta", lambda: None)
    monkeypatch.setattr(store, "runner_log", lambda: [])
    body = client.get("/api/system").json()
    assert body["runner"]["state"] == "NEVER_RUN"
    assert body["components"] == {"runner": False, "playbook": False, "strategy": True, "journal": True, "backtest": False, "alerts": False}
    assert body["strategy"] == "RSI(14) divergence"
    assert body["auto_execution"] is False


def test_system_live_when_recent_cycle(client, monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(app_module, "read_status", lambda: {"started_at": now.isoformat(), "interval_seconds": 3600,
                                                            "last_cycle_finished_at": now.isoformat(), "last_cycle_ok": True, "cycles": 3})
    monkeypatch.setattr(store, "candles", lambda asset: [])
    monkeypatch.setattr(store, "history_report", lambda: {})
    monkeypatch.setattr(store, "playbook_meta", lambda: None)
    monkeypatch.setattr(store, "runner_log", lambda: [])
    assert client.get("/api/system").json()["runner"]["state"] == "LIVE"


def test_quotes_from_stored_bars(client, monkeypatch):
    bars = {a: _bars(a, 260) for a in Asset}
    monkeypatch.setattr(store, "candles", lambda asset: bars[asset])
    monkeypatch.setattr(store, "regime_by_day", lambda asset: ({bars[asset][-2].timestamp: "BULL"}, "SHARED"))
    quotes = client.get("/api/quotes").json()
    btc = next(q for q in quotes if q["asset"] == "BTC")
    # Today's bar is still forming: previous close is yesterday's, last is today's.
    assert btc["prev_close"] == bars[Asset.BTC][-2].close
    assert btc["last"] == bars[Asset.BTC][-1].close
    assert btc["source"] == "STORED" and btc["regime"] == "BULL"
    assert len(btc["sparkline"]) == 30


def test_playbook_404_before_first_build(client, monkeypatch):
    monkeypatch.setattr(store, "playbook_meta", lambda: None)
    monkeypatch.setattr(store, "playbook", lambda asset: None)
    assert client.get("/api/playbook").status_code == 404
    assert client.get("/api/playbook/BTC").status_code == 404


def test_run_button_starts_one_run_and_refuses_a_second(client, monkeypatch):
    from orbit.analysis import jobs

    started = []

    def fake_start(trigger, include_placebo=False, refresh_data=True):
        if started:
            raise jobs.AlreadyRunning(started[0])
        run = jobs.AnalysisRun(id="r1", trigger=trigger, include_placebo=include_placebo, refresh_data=refresh_data,
                               status="queued", created_at=datetime.now(timezone.utc))
        started.append(run)
        return run

    monkeypatch.setattr(app_module.jobs, "start", fake_start)
    first = client.post("/api/analysis/runs", json={"placebo": True, "refresh": False})
    assert first.status_code == 202
    assert first.json()["trigger"] == "manual" and first.json()["include_placebo"] is True
    second = client.post("/api/analysis/runs", json={})
    assert second.status_code == 409 and "already" in second.json()["detail"]


def test_intraday_window(client, monkeypatch):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [Candle(asset=Asset.BTC, timestamp=base + timedelta(hours=h), open=1, high=1, low=1, close=1, volume=1, source="t") for h in range(48)]
    monkeypatch.setattr(store, "candles", lambda asset, timeframe="1d": bars if timeframe == "1h" else [])
    r = client.get("/api/intraday/BTC", params={"at": "2026-01-02T00:30:00Z", "before_hours": 2, "after_hours": 3})
    assert [c["timestamp"][11:13] for c in r.json()] == ["23", "00", "01", "02", "03"]
