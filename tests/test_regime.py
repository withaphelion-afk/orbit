from datetime import datetime, timedelta, timezone

from orbit.core.types import Asset, Candle, Regime
from orbit.features.regime import compute_regime


def _make_trend(asset: Asset, count: int, start_price: float, step: float) -> list[Candle]:
    """Builds a steadily rising (step > 0) or falling (step < 0) price series."""
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    price = start_price
    for i in range(count):
        candles.append(
            Candle(
                asset=asset,
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


def test_bull_regime_when_btc_and_eth_agree():
    btc = _make_trend(Asset.BTC, 250, start_price=100, step=1)
    eth = _make_trend(Asset.ETH, 250, start_price=100, step=1)
    assert compute_regime(btc, eth) == Regime.BULL


def test_bear_regime_when_btc_and_eth_agree():
    btc = _make_trend(Asset.BTC, 250, start_price=1000, step=-1)
    eth = _make_trend(Asset.ETH, 250, start_price=1000, step=-1)
    assert compute_regime(btc, eth) == Regime.BEAR


def test_choppy_when_btc_and_eth_disagree():
    btc = _make_trend(Asset.BTC, 250, start_price=100, step=1)  # rising
    eth = _make_trend(Asset.ETH, 250, start_price=1000, step=-1)  # falling
    assert compute_regime(btc, eth) == Regime.CHOPPY
