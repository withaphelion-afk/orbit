"""Fetch daily OHLCV candles from Binance's public API.

No API key needed for market data — this is a public, read-only endpoint.
Binance calls each bar a "kline"; we convert it into our own Candle type
so the rest of the project never has to know or care where the data came
from.

Binance returns at most 1000 klines per request, so full history is fetched
by paging forward from a start time until a short page comes back.
"""

from __future__ import annotations

from datetime import datetime

from orbit.core.types import Asset, Candle
from orbit.data.dates import from_unix
from orbit.data.http import get_json

BASE_URL = "https://api.binance.com/api/v3/klines"
PAGE_LIMIT = 1000

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
    return _get(asset, {"interval": timeframe, "limit": limit})


def fetch_history(asset: Asset, start: datetime | None = None, timeframe: str = "1d") -> list[Candle]:
    """Every candle from `start` (or the symbol's listing, if None) to now."""
    start_ms = int(start.timestamp() * 1000) if start else 0
    candles: list[Candle] = []
    while True:
        page = _get(asset, {"interval": timeframe, "startTime": start_ms, "limit": PAGE_LIMIT})
        candles.extend(page)
        if len(page) < PAGE_LIMIT:
            return candles
        start_ms = int(page[-1].timestamp.timestamp() * 1000) + 1


def _get(asset: Asset, params: dict) -> list[Candle]:
    symbol = SYMBOLS.get(asset)
    if symbol is None:
        raise ValueError(f"{asset} is not a Binance-traded asset")
    return [_kline_to_candle(asset, symbol, kline) for kline in get_json(BASE_URL, {"symbol": symbol, **params})]


def _kline_to_candle(asset: Asset, symbol: str, kline: list) -> Candle:
    """Binance returns each kline as a fixed-position list, not a dict:
    [open_time, open, high, low, close, volume, close_time, ...].
    We only need the first six fields.
    """
    return Candle(
        asset=asset,
        timestamp=from_unix(kline[0] / 1000),
        open=float(kline[1]),
        high=float(kline[2]),
        low=float(kline[3]),
        close=float(kline[4]),
        volume=float(kline[5]),
        source=f"binance:{symbol}",
    )
