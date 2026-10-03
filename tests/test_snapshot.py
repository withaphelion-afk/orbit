import json
from datetime import datetime, timedelta, timezone

from orbit import snapshot
from orbit.analysis import projection_log
from orbit.api import store
from orbit.core.types import Asset, Candle


def _bars(asset: Asset, n: int, step: timedelta, start: datetime) -> list[Candle]:
    return [
        Candle(asset=asset, timestamp=start + i * step, open=1 + i, high=2 + i, low=0.5 + i, close=1.5 + i, volume=10, source="t")
        for i in range(n)
    ]


def test_snapshot_writes_answers_errors_and_compact_hourly_rows(tmp_path, monkeypatch):
    daily = {a: _bars(a, 40, timedelta(days=1), datetime(2025, 11, 1, tzinfo=timezone.utc)) for a in Asset}
    hourly = {a: _bars(a, 5, timedelta(hours=1), datetime(2025, 12, 31, 22, tzinfo=timezone.utc)) for a in Asset}
    monkeypatch.setattr(store, "candles", lambda asset, timeframe="1d": hourly[asset] if timeframe == "1h" else daily[asset])
    monkeypatch.setattr(store, "playbook", lambda asset: None)
    monkeypatch.setattr(store, "playbook_meta", lambda: None)
    monkeypatch.setattr(projection_log, "LOG_PATH", tmp_path / "projections_log.json")

    n = snapshot.build(tmp_path / "api")
    out = tmp_path / "api"
    assert n > 20

    candles = json.loads((out / "candles" / "BTC.json").read_text(encoding="utf-8"))
    assert len(candles) == 40 and candles[0]["close"] == 1.5

    # A report that doesn't exist yet is published as the API's own error.
    err = json.loads((out / "playbook.json").read_text(encoding="utf-8"))["__error"]
    assert err["status"] == 404 and "playbook" in err["detail"]

    # Projections need a playbook; the track record answers even before anything is recorded.
    for name in ("projections.json", "projections-all.json"):
        assert json.loads((out / name).read_text(encoding="utf-8"))["__error"]["status"] == 404
    track = json.loads((out / "projections-track.json").read_text(encoding="utf-8"))
    assert track["total"]["recorded"] == 0

    # Hourly bars, split by year, as [time, open, high, low, close, volume] rows.
    rows_2025 = json.loads((out / "hourly" / "BTC" / "2025.json").read_text(encoding="utf-8"))
    rows_2026 = json.loads((out / "hourly" / "BTC" / "2026.json").read_text(encoding="utf-8"))
    assert len(rows_2025) == 2 and len(rows_2026) == 3
    assert rows_2025[0][1:] == [1, 2, 0.5, 1.5, 10]

    assert json.loads((out / "snapshot.json").read_text(encoding="utf-8"))["files"] == n


def test_pattern_key_is_reversible_and_matches_the_web_client():
    key = snapshot.pattern_key("MARS:INGRESS:Aries|VAKRI")
    assert key == "4d4152533a494e47524553533a41726965737c56414b5249"  # same as web/src/api/static.test.ts
    assert bytes.fromhex(key).decode() == "MARS:INGRESS:Aries|VAKRI"
