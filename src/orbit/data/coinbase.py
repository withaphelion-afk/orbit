"""Fetch daily candles from Coinbase Exchange's public API.

Used only for ETH history before Binance listed ETHUSDT (August 2017):
Coinbase has ETH-USD daily bars from May 2016. No API key needed. The
endpoint returns at most 300 bars per request, newest first, as
[time, low, high, open, close, volume] — note low/high come before open.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from orbit.core.types import Asset, Candle
from orbit.data.dates import from_unix
from orbit.data.http import get_json

BASE_URL = "https://api.exchange.coinbase.com/products/{product}/candles"
PAGE_DAYS = 300


def fetch_history(asset: Asset, product: str, start: datetime, end: datetime | None = None) -> list[Candle]:
    """Daily candles for `product` (e.g. "ETH-USD") from `start` to `end` (default: now)."""
    end = end or datetime.now(timezone.utc)
    by_day: dict[datetime, Candle] = {}
    cursor = start
    while cursor < end:
        window_end = min(cursor + timedelta(days=PAGE_DAYS - 1), end)
        rows = get_json(
            BASE_URL.format(product=product),
            {"granularity": 86_400, "start": cursor.isoformat(), "end": window_end.isoformat()},
        )
        for t, low, high, open_, close, volume in rows:
            candle = Candle(
                asset=asset,
                timestamp=from_unix(t),
                open=float(open_),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=float(volume),
                source=f"coinbase:{product}",
            )
            by_day[candle.timestamp] = candle
        cursor = window_end + timedelta(days=1)
        time.sleep(0.25)  # public endpoint rate limit is ~10 req/s; stay well under it
    return [by_day[d] for d in sorted(by_day)]
