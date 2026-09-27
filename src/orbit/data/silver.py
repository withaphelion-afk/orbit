"""Fetch daily OHLCV candles for silver futures (ticker SI=F) from Yahoo
Finance's public chart API.

No API key needed. Silver isn't on a crypto exchange, so it gets its own
fetcher instead of living in binance.py — same output type (Candle)
though, so nothing downstream needs to know the difference.
"""

from __future__ import annotations

import requests

from orbit.core.types import Asset, Candle

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/SI=F"

# Yahoo's interval strings differ from Binance's: "1d" works the same,
# but not every timeframe lines up 1:1.
RANGE_BY_TIMEFRAME = {
    "1d": "2y",
    "1h": "60d",
}


def fetch_candles(timeframe: str = "1d") -> list[Candle]:
    """Fetch silver daily candles. `timeframe` uses Yahoo's interval strings."""
    range_ = RANGE_BY_TIMEFRAME.get(timeframe, "2y")

    response = requests.get(
        BASE_URL,
        params={"interval": timeframe, "range": range_},
        timeout=10,
        headers={"User-Agent": "Mozilla/5.0"},  # Yahoo blocks requests with no UA
    )
    response.raise_for_status()
    payload = response.json()

    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]

    candles = []
    for i, ts in enumerate(timestamps):
        # Yahoo sometimes has null values for illiquid bars (holidays, etc.) — skip those.
        if quote["open"][i] is None:
            continue
        candles.append(
            Candle(
                asset=Asset.SILVER,
                timestamp=ts,  # unix seconds
                open=float(quote["open"][i]),
                high=float(quote["high"][i]),
                low=float(quote["low"][i]),
                close=float(quote["close"][i]),
                volume=float(quote["volume"][i] or 0),
            )
        )
    return candles
