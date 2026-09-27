from datetime import datetime, timedelta, timezone

from orbit.core.types import Asset, Candle
from orbit.features.store import load_features, save_features
from orbit.features.technical import compute_technical_features


def _make_candles(count: int, start_price: float = 100.0, step: float = 0.1) -> list[Candle]:
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = start_price
    candles = []
    for i in range(count):
        candles.append(
            Candle(
                asset=Asset.BTC,
                timestamp=base_time + timedelta(days=i),
                open=price,
                high=price + 1,
                low=price - 1,
                close=price,
                volume=100.0,
            )
        )
        price += step
    return candles


def test_technical_features_need_200_candles():
    assert compute_technical_features(_make_candles(199)) == []
    records = compute_technical_features(_make_candles(210))
    names = {r.name for r in records}
    assert names == {"return_1d", "close_vs_sma50", "close_vs_sma200", "volatility_20d"}


def test_technical_feature_values_are_sane_for_steady_uptrend():
    records = compute_technical_features(_make_candles(210))
    latest_return = [r for r in records if r.name == "return_1d"][-1]
    # A steadily rising price series should show a small positive daily return.
    assert latest_return.value > 0


def test_feature_store_roundtrip(tmp_path, monkeypatch):
    import orbit.features.store as store

    monkeypatch.setattr(store, "FEATURES_DIR", tmp_path)

    records = compute_technical_features(_make_candles(210))
    save_features(records)

    loaded = load_features(Asset.BTC, "return_1d")
    assert len(loaded) == len([r for r in records if r.name == "return_1d"])
