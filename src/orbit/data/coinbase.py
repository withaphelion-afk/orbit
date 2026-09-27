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
from orbit.data.dates import bar_time
from orbit.data.http import get_json

BASE_URL = "https://api.exchange.coinbase.com/products/{product}/candles"
PAGE_BARS = 300
GRANULARITY = {"1d": 86_400, "1h": 3_600}


def fetch_history(asset: Asset, product: str, start: datetime, end: datetime | None = None, timeframe: str = "1d") -> list[Candle]:
    """Candles for `product` (e.g. "ETH-USD") from `start` to `end` (default: now); daily or hourly."""
    end = end or datetime.now(timezone.utc)
    step = timedelta(seconds=GRANULARITY[timeframe])
    by_day: dict[datetime, Candle] = {}
    cursor = start
    while cursor < end:
        window_end = min(cursor + step * (PAGE_BARS - 1), end)
        rows = get_json(
            BASE_URL.format(product=product),
            {"granularity": GRANULARITY[timeframe], "start": cursor.isoformat(), "end": window_end.isoformat()},
        )
        for t, low, high, open_, close, volume in rows:
            candle = Candle(
                asset=asset,
                timestamp=bar_time(t, timeframe),
                open=float(open_),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=float(volume),
                source=f"coinbase:{product}",
            )
            by_day[candle.timestamp] = candle
        cursor = window_end + step
        time.sleep(0.25)  # public endpoint rate limit is ~10 req/s; stay well under it
    return [by_day[d] for d in sorted(by_day)]
