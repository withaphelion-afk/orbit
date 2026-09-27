"""Manual script: fetch and store the latest candles for BTC/ETH/SOL/silver.

Run it with:
    uv run python scripts/fetch_data.py
"""

from orbit.data.pipeline import fetch_all_prices

if __name__ == "__main__":
    fetch_all_prices()
    print("Fetched and saved candles for BTC, ETH, SOL, and silver.")
