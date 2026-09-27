"""Fetch daily BTC/USD candles from Bitstamp's public OHLC API.

Used only for BTC history before Binance listed BTCUSDT (August 2017):
Bitstamp is one of the few venues with continuous USD daily bars back to
2011. No API key needed. At most 1000 bars per request, so we page forward.
"""

from __future__ import annotations

from datetime import datetime, timezone

from orbit.core.types import Asset, Candle
from orbit.data.dates import bar_time
from orbit.data.http import get_json

BASE_URL = "https://www.bitstamp.net/api/v2/ohlc/{pair}/"
PAGE_LIMIT = 1000
STEP_SECONDS = {"1d": 86_400, "1h": 3_600}


def fetch_history(asset: Asset, pair: str, start: datetime, end: datetime | None = None, timeframe: str = "1d") -> list[Candle]:
    """Candles for `pair` (e.g. "btcusd") from `start` up to `end` (default: now); daily or hourly."""
    step = STEP_SECONDS[timeframe]
    end_ts = int((end or datetime.now(timezone.utc)).timestamp())
    cursor = int(start.timestamp())
    candles: list[Candle] = []
    while cursor < end_ts:
        payload = get_json(BASE_URL.format(pair=pair), {"step": step, "limit": PAGE_LIMIT, "start": cursor})
        rows = payload["data"]["ohlc"]
        if not rows:
            break
        for row in rows:
            ts = int(row["timestamp"])
            if ts > end_ts:
                break
            candles.append(
                Candle(
                    asset=asset,
                    timestamp=bar_time(ts, timeframe),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    source=f"bitstamp:{pair}",
                )
            )
        last = int(rows[-1]["timestamp"])
        if len(rows) < PAGE_LIMIT or last >= end_ts:
            break
        cursor = last + step
    return candles
