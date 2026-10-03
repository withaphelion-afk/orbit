"""Reusable data-fetching steps, shared by the one-off scripts and the
24/7 runner so the fetch logic only lives in one place.
"""

from __future__ import annotations

from orbit.core.types import Asset
from orbit.data.gaps import assert_no_gaps
from orbit.data.history import TIMEFRAMES, update_history
from orbit.data.storage import load_candles

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


def verify_prices() -> None:
    """Raise DataGapError if any stored series has holes the market doesn't explain."""
    for asset in ALL_ASSETS:
        for timeframe in TIMEFRAMES:
            candles = load_candles(asset, timeframe)
            if candles:
                assert_no_gaps(asset, timeframe, candles)


def fetch_all_ephemeris() -> int:
    """Bring the Vedic sky up to date: sidereal positions of the 9 grahas every
    6 hours from 2000 to EPHEMERIS_YEARS_AHEAD ahead, and every event on them
    (orbit/vedic). Cached; only rebuilt when it no longer reaches far enough
    ahead. Returns the number of events.
    """
    from orbit.vedic.events import load_events

    return len(load_events())
