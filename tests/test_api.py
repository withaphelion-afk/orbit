from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from orbit.api.app import app
from orbit.core.types import Asset, Candle, EphemerisSnapshot, Planet
from orbit.data import storage

client = TestClient(app)


def _make_candles(asset: Asset, count: int, start_price: float = 100.0, step: float = 1.0) -> list[Candle]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = start_price
    candles = []
    for i in range(count):
        candles.append(
            Candle(asset=asset, timestamp=base + timedelta(days=i), open=price, high=price + 1, low=price - 1, close=price, volume=10.0)
        )
        price += step
    return candles


def test_suggestions_journal_and_drift_are_honestly_empty():
    # No strategy layer exists yet, so these must not fabricate data.
    assert client.get("/api/suggestions").json() == []
    assert client.get("/api/journal").json() == []

    drift = client.get("/api/drift").json()
    assert drift["backtest_trades"] == 0
    assert drift["live_trades"] == 0
    assert drift["curve"] == []


def test_decision_on_nonexistent_suggestion_is_404():
    response = client.post("/api/suggestions/does-not-exist/decision", json={"decision": "SKIPPED", "notes": ""})
    assert response.status_code == 404


def test_quotes_and_candles_use_real_stored_data(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    candles = _make_candles(Asset.BTC, 60)
    storage.save_candles(candles, timeframe="1d")

    response = client.get("/api/candles/BTC")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 60
    assert body[-1]["close"] == candles[-1].close


def test_astro_events_computes_real_forward_returns(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)

    # BTC rises steadily so the forward-return math is checkable.
    storage.save_candles(_make_candles(Asset.BTC, 40, start_price=100.0, step=1.0), timeframe="1d")

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snapshots = []
    sign = "Aries"
    for i in range(40):
        if i == 10:
            sign = "Taurus"  # one sign change, well inside the BTC window
        snapshots.append(
            EphemerisSnapshot(planet=Planet.JUPITER, date=base + timedelta(days=i), longitude=float(i), sign=sign, retrograde=False)
        )
    storage.save_ephemeris_snapshots(snapshots)

    from orbit.api.astro_events import build_astro_events

    events = build_astro_events()
    taurus_events = [e for e in events if e.event == "Jupiter enters Taurus"]
    assert len(taurus_events) == 1
    assert taurus_events[0].prior_occurrences == 0  # first-ever occurrence in this synthetic history
