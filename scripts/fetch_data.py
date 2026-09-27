"""Manual script: fetch and store the latest candles for all tracked crypto assets.

Run it with:
    uv run python scripts/fetch_data.py
"""

from __future__ import annotations

from orbit.core.types import Asset
from orbit.data import binance, silver
from orbit.data.storage import save_candles

TIMEFRAME = "1d"

if __name__ == "__main__":
    for asset in [Asset.BTC, Asset.ETH, Asset.SOL]:
        candles = binance.fetch_candles(asset, timeframe=TIMEFRAME)
        path = save_candles(candles, timeframe=TIMEFRAME)
        print(f"{asset.value}: saved {len(candles)} candles -> {path}")

    silver_candles = silver.fetch_candles(timeframe=TIMEFRAME)
    path = save_candles(silver_candles, timeframe=TIMEFRAME)
    print(f"SILVER: saved {len(silver_candles)} candles -> {path}")
