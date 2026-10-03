"""Silver's live quote: Yahoo Finance's silver futures (SI=F), delayed.

Silver's price history comes from Dukascopy spot (data/dukascopy.py); Yahoo
only serves two years of hourly bars and its futures jump at every contract
roll. Its quote endpoint is still the simplest free source for a current
price, which the API's live feed polls (api/live.py).
"""

from __future__ import annotations

from orbit.data.http import get_json

TICKER = "SI=F"
BASE_URL = f"https://query1.finance.yahoo.com/v8/finance/chart/{TICKER}"


def fetch_latest_price() -> float | None:
    """The latest traded price Yahoo reports (delayed for futures)."""
    payload = get_json(BASE_URL, {"interval": "1d", "range": "1d"}, timeout=10)
    return payload["chart"]["result"][0]["meta"].get("regularMarketPrice")
