from datetime import datetime, timezone

from orbit.core.types import Asset, Candle
from orbit.data import storage


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)

    candles = [
        Candle(
            asset=Asset.BTC,
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            open=100.0,
            high=110.0,
            low=95.0,
            close=105.0,
            volume=1234.5,
        )
    ]

    storage.save_candles(candles, timeframe="1d")
    loaded = storage.load_candles(Asset.BTC, timeframe="1d")

    assert len(loaded) == 1
    assert loaded[0].close == 105.0
    assert loaded[0].asset == Asset.BTC
