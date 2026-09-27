"""Fetch daily OHLCV candles for silver futures (ticker SI=F) from Yahoo
Finance's public chart API.

No API key needed. Silver isn't on a crypto exchange, so it gets its own
fetcher instead of living in binance.py — same output type (Candle)
though, so nothing downstream needs to know the difference.

Two details matter for full history:
- `range=max` silently downsamples to monthly bars, so history is requested
  with explicit period1/period2 instead, which keeps daily bars back to 2000.
- Yahoo stamps each bar at New York midnight (04:00/05:00 UTC). Bars are
  dated by their New York calendar day using the offset Yahoo reports.
SI=F is a continuous front-month contract, so there are small price jumps at
each roll; percentile-based analysis on returns is fairly robust to that.
"""

from __future__ import annotations

import time
from datetime import datetime

from orbit.core.types import Asset, Candle
from orbit.data.dates import from_unix
from orbit.data.http import get_json

TICKER = "SI=F"
BASE_URL = f"https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}"

# Yahoo's interval strings differ from Binance's: "1d" works the same,
# but not every timeframe lines up 1:1.
RANGE_BY_TIMEFRAME = {
    "1d": "2y",
    "1h": "60d",
}


def fetch_candles(timeframe: str = "1d") -> list[Candle]:
    """Recent silver candles (the last ~2 years for daily)."""
    return _get({"interval": timeframe, "range": RANGE_BY_TIMEFRAME.get(timeframe, "2y")})


def fetch_history(start: datetime | None = None) -> list[Candle]:
    """Every daily silver candle from `start` (default: Yahoo's first, Aug 2000) to now."""
    period1 = int(start.timestamp()) if start else 0
    return _get({"interval": "1d", "period1": period1, "period2": int(time.time())})


def fetch_latest_price() -> float | None:
    """The latest traded price Yahoo reports (delayed for futures)."""
    payload = get_json(BASE_URL, {"interval": "1d", "range": "1d"}, timeout=10)
    return payload["chart"]["result"][0]["meta"].get("regularMarketPrice")


def _get(params: dict) -> list[Candle]:
    result = get_json(BASE_URL, params, timeout=30)["chart"]["result"][0]
    offset = int(result["meta"].get("gmtoffset", 0))
    timestamps = result.get("timestamp", [])
    quote = result["indicators"]["quote"][0]

    by_day: dict[datetime, Candle] = {}
    for i, ts in enumerate(timestamps):
        # Yahoo sometimes has null values for illiquid bars (holidays, etc.) — skip those.
        if None in (quote["open"][i], quote["high"][i], quote["low"][i], quote["close"][i]):
            continue
        candle = Candle(
            asset=Asset.SILVER,
            timestamp=from_unix(ts, offset),
            open=float(quote["open"][i]),
            high=float(quote["high"][i]),
            low=float(quote["low"][i]),
            close=float(quote["close"][i]),
            volume=float(quote["volume"][i] or 0),
            source=f"yahoo:{TICKER}",
        )
        by_day[candle.timestamp] = candle  # the live bar can repeat the last day; keep the latest
    return [by_day[d] for d in sorted(by_day)]
