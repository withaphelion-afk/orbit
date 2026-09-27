"""Fetch daily OHLCV candles from Binance's public API.

No API key needed for market data — this is a public, read-only endpoint.
Binance calls each bar a "kline"; we convert it into our own Candle type
so the rest of the project never has to know or care where the data came
from.
"""

from __future__ import annotations

import requests

from orbit.core.types import Asset, Candle

BASE_URL = "https://api.binance.com/api/v3/klines"

# Binance's trading pair symbols for each crypto asset we track.
# Silver isn't on Binance, so it isn't in this map — see silver.py instead.
SYMBOLS = {
    Asset.BTC: "BTCUSDT",
    Asset.ETH: "ETHUSDT",
    Asset.SOL: "SOLUSDT",
}


def fetch_candles(asset: Asset, timeframe: str = "1d", limit: int = 500) -> list[Candle]:
    """Fetch the most recent `limit` candles for `asset` at the given timeframe.

    timeframe uses Binance's own strings: "1d" (daily), "1h" (hourly), etc.
    limit is capped at 1000 by Binance's API.
    """
    symbol = SYMBOLS.get(asset)
    if symbol is None:
        raise ValueError(f"{asset} is not a Binance-traded asset")

    response = requests.get(
        BASE_URL,
        params={"symbol": symbol, "interval": timeframe, "limit": limit},
        timeout=10,
    )
    response.raise_for_status()
    raw_klines = response.json()

    return [_kline_to_candle(asset, kline) for kline in raw_klines]


def _kline_to_candle(asset: Asset, kline: list) -> Candle:
    """Binance returns each kline as a fixed-position list, not a dict:
    [open_time, open, high, low, close, volume, close_time, ...].
    We only need the first six fields.
    """
    open_time_ms = kline[0]
    return Candle(
        asset=asset,
        timestamp=open_time_ms / 1000,  # pydantic accepts unix seconds for datetime
        open=float(kline[1]),
        high=float(kline[2]),
        low=float(kline[3]),
        close=float(kline[4]),
        volume=float(kline[5]),
    )
