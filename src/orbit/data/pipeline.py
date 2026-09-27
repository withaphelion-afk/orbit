"""Reusable data-fetching steps, shared by the one-off scripts and the
24/7 runner so the fetch logic only lives in one place.
"""

from __future__ import annotations

from datetime import timedelta

from orbit.config.settings import EPHEMERIS_YEARS_AHEAD, EPHEMERIS_YEARS_OF_HISTORY
from orbit.core.types import Asset, Planet
from orbit.data import ephemeris
from orbit.data.dates import today_utc
from orbit.data.history import TIMEFRAMES, update_history
from orbit.data.storage import save_ephemeris_snapshots

ALL_ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL, Asset.SILVER]


def fetch_all_prices() -> dict[str, dict | None]:
    """Bring every asset's stored daily and hourly history up to date.

    The first run builds full stitched histories (a few hundred requests per
    timeframe); later runs only fetch the last few days. Returns each
    asset/timeframe's stitch report when a full build happened, else None.
    """
    reports = {}
    for asset in ALL_ASSETS:
        for timeframe in TIMEFRAMES:
            _, report = update_history(asset, timeframe)
            reports[f"{asset.value} {timeframe}"] = report
    return reports


def fetch_all_ephemeris(years: int = EPHEMERIS_YEARS_OF_HISTORY, years_ahead: int = EPHEMERIS_YEARS_AHEAD) -> None:
    """Planetary positions for every tracked planet, from `years` back to
    `years_ahead` forward (future positions are what "upcoming transits" come from).

    Runs entirely offline after the ephemeris kernel is downloaded once,
    and is fast even for decades of history (see data/ephemeris.py), so
    it's safe to recompute in full on every runner cycle rather than
    needing incremental updates.
    """
    start_date = today_utc() - timedelta(days=years * 365)
    days = (years + years_ahead) * 365
    for planet in Planet:
        snapshots = ephemeris.backfill_planet(planet, start_date, days=days)
        save_ephemeris_snapshots(snapshots)
