"""Lightweight current-price lookups for the WebSocket tick feed.

Separate from data/binance.py and data/silver.py (which fetch full OHLCV
history for the feature store) — this only needs a single current price,
polled frequently, so it hits each source's lightest endpoint.
"""

from __future__ import annotations

import requests

from orbit.core.types import Asset

BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/SI=F"

BINANCE_SYMBOLS = {
    Asset.BTC: "BTCUSDT",
    Asset.ETH: "ETHUSDT",
    Asset.SOL: "SOLUSDT",
}


def fetch_current_price(asset: Asset) -> float | None:
    """Best-effort current price. Returns None on any failure — the
    WebSocket loop skips a tick rather than crashing the connection.
    """
    try:
        if asset in BINANCE_SYMBOLS:
            response = requests.get(
                BINANCE_TICKER_URL, params={"symbol": BINANCE_SYMBOLS[asset]}, timeout=5
            )
            response.raise_for_status()
            return float(response.json()["price"])

        if asset == Asset.SILVER:
            response = requests.get(
                YAHOO_QUOTE_URL,
                params={"interval": "1d", "range": "1d"},
                timeout=5,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
            result = response.json()["chart"]["result"][0]
            return float(result["meta"]["regularMarketPrice"])
    except (requests.RequestException, KeyError, ValueError, IndexError):
        return None

    return None
