"""Load stored prices and ephemeris as plain numpy arrays for the research.

Only *completed* daily bars are used: today's bar is still forming, and a
half-finished bar would quietly bias every forward return that touches it.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass

import numpy as np

from orbit.config.settings import DATA_DIR, TIMEFRAME
from orbit.core.types import Asset, Planet
from orbit.data.dates import today_utc
from orbit.data.ephemeris import ZODIAC_SIGNS
from orbit.data.storage import load_candles


def day64(d) -> np.datetime64:
    """A datetime (tz-aware or not) as numpy day precision."""
    return np.datetime64(d.replace(tzinfo=None), "D")


@dataclass
class PriceSeries:
    asset: Asset
    dates: np.ndarray  # datetime64[D], ascending
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray

    def __len__(self) -> int:
        return len(self.dates)


@dataclass
class PlanetSeries:
    planet: Planet
    dates: np.ndarray  # datetime64[D], ascending, one per calendar day
    sign_index: np.ndarray  # 0 (Aries) .. 11 (Pisces)
    retrograde: np.ndarray  # bool
    longitude: np.ndarray | None = None  # ecliptic degrees, 0-360


def load_price_series(asset: Asset, until=None) -> PriceSeries:
    cutoff = day64(until or today_utc())
    candles = [c for c in load_candles(asset, TIMEFRAME) if day64(c.timestamp) < cutoff]
    return PriceSeries(
        asset=asset,
        dates=np.array([day64(c.timestamp) for c in candles], dtype="datetime64[D]"),
        open=np.array([c.open for c in candles], dtype=float),
        high=np.array([c.high for c in candles], dtype=float),
        low=np.array([c.low for c in candles], dtype=float),
        close=np.array([c.close for c in candles], dtype=float),
    )


def load_planet_series() -> dict[Planet, PlanetSeries]:
    """Every stored planet's daily series. Reads the CSVs directly rather than
    through EphemerisSnapshot objects: 60+ years x 10 planets is ~230k rows,
    and building a model per row made this take seconds instead of a blink."""
    sign_of = {name: i for i, name in enumerate(ZODIAC_SIGNS)}
    out = {}
    for planet in Planet:
        path = DATA_DIR / "ephemeris" / f"{planet.value}.csv"
        if not path.exists():
            continue
        with path.open(newline="") as f:
            rows = list(csv.reader(f))[1:]
        if not rows:
            continue
        out[planet] = PlanetSeries(
            planet=planet,
            dates=np.array([r[0][:10] for r in rows], dtype="datetime64[D]"),
            sign_index=np.array([sign_of[r[2]] for r in rows], dtype=int),
            retrograde=np.array([r[3] == "True" for r in rows], dtype=bool),
            longitude=np.array([float(r[1]) for r in rows]),
        )
    return out
