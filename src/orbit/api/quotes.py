"""Builds Quote and Signal views from already-stored candles and features.

No network calls here — this reads whatever the runner last fetched, same
as everything else in the API. Live current-price ticks are a separate,
lightweight path (see live_prices.py) used only for the WebSocket feed.
"""

from __future__ import annotations

from orbit.api.schemas import Quote
from orbit.config.settings import TIMEFRAME
from orbit.core.types import Asset, Direction, Regime, Signal
from orbit.data.storage import load_candles
from orbit.features.store import load_features

SPARKLINE_DAYS = 30

_REGIME_FROM_VALUE = {1.0: Regime.BULL, -1.0: Regime.BEAR, 0.0: Regime.CHOPPY}


def _asset_regime(asset: Asset) -> Regime:
    records = load_features(asset, "regime")
    if not records:
        return Regime.CHOPPY
    return _REGIME_FROM_VALUE.get(records[-1].value, Regime.CHOPPY)


def build_quote(asset: Asset) -> Quote | None:
    candles = load_candles(asset, TIMEFRAME)
    if len(candles) < 2:
        return None

    latest = candles[-1]
    previous = candles[-2]
    sparkline = [c.close for c in candles[-SPARKLINE_DAYS:]]

    return Quote(
        asset=asset,
        last=latest.close,
        prev_close=previous.close,
        day_high=latest.high,
        day_low=latest.low,
        sparkline=sparkline,
        regime=_asset_regime(asset),
        source="LIVE",
    )


def build_quotes(assets: list[Asset]) -> list[Quote]:
    quotes = [build_quote(asset) for asset in assets]
    return [q for q in quotes if q is not None]


def build_signals(asset: Asset) -> list[Signal]:
    """Descriptive signals from the feature store — what we currently
    observe, not a trade recommendation (there is no strategy layer yet).
    """
    signals = []
    latest_by_name = {}
    for name in ["return_1d", "close_vs_sma50", "close_vs_sma200", "volatility_20d", "regime"]:
        records = load_features(asset, name)
        if records:
            latest_by_name[name] = records[-1]

    if "close_vs_sma50" in latest_by_name:
        record = latest_by_name["close_vs_sma50"]
        direction = Direction.LONG if record.value > 0 else Direction.SHORT
        signals.append(
            Signal(
                name="close_vs_sma50",
                asset=asset,
                timestamp=record.date,
                direction=direction,
                strength=min(abs(record.value) * 5, 1.0),
                reason=f"Price is {abs(record.value) * 100:.1f}% {'above' if record.value > 0 else 'below'} its 50-day average",
            )
        )

    if "close_vs_sma200" in latest_by_name:
        record = latest_by_name["close_vs_sma200"]
        direction = Direction.LONG if record.value > 0 else Direction.SHORT
        signals.append(
            Signal(
                name="close_vs_sma200",
                asset=asset,
                timestamp=record.date,
                direction=direction,
                strength=min(abs(record.value) * 3, 1.0),
                reason=f"Price is {abs(record.value) * 100:.1f}% {'above' if record.value > 0 else 'below'} its 200-day average",
            )
        )

    if "regime" in latest_by_name:
        record = latest_by_name["regime"]
        regime = _REGIME_FROM_VALUE.get(record.value, Regime.CHOPPY)
        if regime != Regime.CHOPPY:
            direction = Direction.LONG if regime == Regime.BULL else Direction.SHORT
            signals.append(
                Signal(
                    name="regime_gate",
                    asset=asset,
                    timestamp=record.date,
                    direction=direction,
                    strength=1.0,
                    reason=f"Shared BTC/ETH regime gate reads {regime.value}",
                )
            )

    return signals
