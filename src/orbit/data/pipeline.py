"""Reusable data-fetching steps, shared by the one-off scripts and the
24/7 runner so the fetch logic only lives in one place.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from orbit.config.settings import TIMEFRAME
from orbit.core.types import Asset, Planet
from orbit.data import binance, ephemeris, silver
from orbit.data.storage import save_candles, save_ephemeris_snapshots

CRYPTO_ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL]
EPHEMERIS_YEARS_OF_HISTORY = 60


def fetch_all_prices() -> None:
    """Fetch and store the latest candles for BTC, ETH, SOL, and silver."""
    for asset in CRYPTO_ASSETS:
        candles = binance.fetch_candles(asset, timeframe=TIMEFRAME)
        save_candles(candles, timeframe=TIMEFRAME)

    silver_candles = silver.fetch_candles(timeframe=TIMEFRAME)
    save_candles(silver_candles, timeframe=TIMEFRAME)


def fetch_all_ephemeris(years: int = EPHEMERIS_YEARS_OF_HISTORY) -> None:
    """Backfill planetary positions for every tracked planet.

    Runs entirely offline after the ephemeris kernel is downloaded once,
    and is fast even for decades of history (see data/ephemeris.py), so
    it's safe to recompute in full on every runner cycle rather than
    needing incremental updates.
    """
    days = years * 365
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    for planet in Planet:
        snapshots = ephemeris.backfill_planet(planet, start_date, days=days)
        save_ephemeris_snapshots(snapshots)
