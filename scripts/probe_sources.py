"""Check which price sources answer from this machine (or cloud host).

Some venues block whole regions: api.binance.com refuses US addresses, which
is where GitHub Actions and most free hosts run. Run this before trusting a
new host:
    uv run python scripts/probe_sources.py
"""

from __future__ import annotations

import sys

import requests

from orbit.data.http import USER_AGENT

PROBES = {
    "binance (api.binance.com)": ("https://api.binance.com/api/v3/klines", {"symbol": "BTCUSDT", "interval": "1d", "limit": 2}),
    "binance (data-api.binance.vision)": ("https://data-api.binance.vision/api/v3/klines", {"symbol": "BTCUSDT", "interval": "1d", "limit": 2}),
    "binance ticker (data-api.binance.vision)": ("https://data-api.binance.vision/api/v3/ticker/price", {"symbol": "BTCUSDT"}),
    "bitstamp": ("https://www.bitstamp.net/api/v2/ohlc/btcusd/", {"step": 86400, "limit": 2}),
    "coinbase": ("https://api.exchange.coinbase.com/products/ETH-USD/candles", {"granularity": 86400}),
    "yahoo (silver futures)": ("https://query1.finance.yahoo.com/v8/finance/chart/SI=F", {"interval": "1d", "range": "5d"}),
    "dukascopy (spot silver)": ("https://datafeed.dukascopy.com/datafeed/XAGUSD/2024/00/BID_candles_hour_1.bi5", None),
}


def main() -> int:
    failed = 0
    for name, (url, params) in PROBES.items():
        try:
            r = requests.get(url, params=params, timeout=20, headers={"User-Agent": USER_AGENT})
            ok = r.status_code == 200 and len(r.content) > 0
            detail = f"HTTP {r.status_code}, {len(r.content)} bytes"
        except requests.RequestException as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        failed += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {name:42s} {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
