from datetime import datetime, timezone

from orbit.core.types import Asset, Candle


def test_candle_construction():
    candle = Candle(
        asset=Asset.BTC,
        timestamp=datetime.now(timezone.utc),
        open=100.0,
        high=110.0,
        low=95.0,
        close=105.0,
        volume=1234.5,
    )
    assert candle.asset == Asset.BTC
    assert candle.close == 105.0
