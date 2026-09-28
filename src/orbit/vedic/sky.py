"""Sidereal positions of the 9 grahas, sampled every 6 hours, and exact-time search.

Longitudes come from Skyfield / JPL DE421 in the J2000 ecliptic frame (fixed to
the stars), minus the Chitrapaksha ayanamsa (see zodiac.py). Rahu is the mean
lunar node (Meeus), converted from the equinox of date to J2000 by removing
accumulated precession; Ketu is Rahu + 180.

Six-hour samples are fine enough that no graha skips a nakshatra between two
samples (the Moon moves at most ~4 degrees in 6 hours, a nakshatra is 13.3).
Every event is then refined to the second by bisection on the same functions,
so sampling only decides *which* interval to search.

The sample grid is cached in data/vedic/sky.npz and rebuilt when it no longer
reaches two years ahead of today.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
from skyfield.api import Star

from orbit.config.settings import DATA_DIR, EPHEMERIS_YEARS_AHEAD
from orbit.core.types import Planet
from orbit.data.ephemeris import _get_ephemeris
from orbit.vedic.zodiac import GRAHAS

STEP_DAYS = 0.25
SKY_START = datetime(2000, 1, 1, tzinfo=timezone.utc)
CACHE = DATA_DIR / "vedic" / "sky.npz"
ITERATIONS = 26  # a 6-12 hour bracket halved 26 times: well under a second

BODY = {
    Planet.SUN: "sun", Planet.MOON: "moon", Planet.MARS: "mars barycenter", Planet.MERCURY: "mercury barycenter",
    Planet.JUPITER: "jupiter barycenter", Planet.VENUS: "venus barycenter", Planet.SATURN: "saturn barycenter",
}
# Chitra (Spica), Hipparcos J2000 position and proper motion.
SPICA = Star(ra_hours=(13, 25, 11.57937), dec_degrees=(-11, -9, -40.7501), ra_mas_per_year=-42.35, dec_mas_per_year=-30.67)


@lru_cache(maxsize=1)
def ayanamsa_j2000() -> float:
    """Chitrapaksha ayanamsa in the J2000 ecliptic frame: Spica's longitude minus 180."""
    eph, ts = _get_ephemeris()
    _, lon, _ = eph["earth"].at(ts.tt_jd(2451545.0)).observe(SPICA).ecliptic_latlon()
    return float(lon.degrees - 180.0)


def wrap(x):
    """Signed angle difference in (-180, 180]."""
    return (np.asarray(x) + 540.0) % 360.0 - 180.0


def _mean_node_j2000(tt: np.ndarray) -> np.ndarray:
    T = (np.asarray(tt, dtype=float) - 2451545.0) / 36525.0
    omega_of_date = 125.0445479 - 1934.1362891 * T + 0.0020754 * T**2 + T**3 / 467441 - T**4 / 60616000
    precession = (5028.796195 * T + 1.1054348 * T**2) / 3600.0
    return (omega_of_date - precession) % 360.0


def sidereal_longitude(graha: Planet, tt) -> np.ndarray:
    """Sidereal longitude (degrees, 0-360) of a graha at TT Julian dates."""
    tt = np.atleast_1d(np.asarray(tt, dtype=float))
    ay = ayanamsa_j2000()
    if graha == Planet.RAHU:
        return (_mean_node_j2000(tt) - ay) % 360.0
    if graha == Planet.KETU:
        return (_mean_node_j2000(tt) + 180.0 - ay) % 360.0
    eph, ts = _get_ephemeris()
    _, lon, _ = eph["earth"].at(ts.tt_jd(tt)).observe(eph[BODY[graha]]).apparent().ecliptic_latlon()
    return (np.atleast_1d(lon.degrees) - ay) % 360.0


def speed(graha: Planet, tt, step: float = 1 / 24) -> np.ndarray:
    """Degrees per day (negative while vakri)."""
    tt = np.atleast_1d(np.asarray(tt, dtype=float))
    return wrap(sidereal_longitude(graha, tt + step) - sidereal_longitude(graha, tt - step)) / (2 * step)


def bisect(f, lo, hi) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised bisection for a sign change of f on [lo, hi]. Returns (root, bracketed?)."""
    lo, hi = np.array(lo, dtype=float), np.array(hi, dtype=float)
    f_lo, f_hi = f(lo), f(hi)
    ok = np.sign(f_lo) != np.sign(f_hi)
    for _ in range(ITERATIONS):
        mid = (lo + hi) / 2
        f_mid = f(mid)
        left = np.sign(f_mid) == np.sign(f_lo)
        lo, f_lo, hi = np.where(left, mid, lo), np.where(left, f_mid, f_lo), np.where(left, hi, mid)
    return (lo + hi) / 2, ok


def tt_of(d: datetime) -> float:
    _, ts = _get_ephemeris()
    return float(ts.from_datetime(d).tt)


def to_datetime(tt: float) -> datetime:
    _, ts = _get_ephemeris()
    return ts.tt_jd(float(tt)).utc_datetime().replace(microsecond=0).astimezone(timezone.utc)


@dataclass
class Sky:
    tt: np.ndarray  # TT Julian dates of the samples
    lon: dict[Planet, np.ndarray]  # sidereal longitude per graha
    spd: dict[Planet, np.ndarray]  # degrees/day per graha

    def __len__(self) -> int:
        return len(self.tt)


def build_sky(start: datetime = SKY_START, end: datetime | None = None) -> Sky:
    if end is None:
        now = datetime.now(timezone.utc)
        end = now.replace(year=now.year + EPHEMERIS_YEARS_AHEAD)
    tt = np.arange(tt_of(start), tt_of(end), STEP_DAYS)
    lon = {g: sidereal_longitude(g, tt) for g in GRAHAS}
    spd = {g: speed(g, tt) for g in GRAHAS}
    return Sky(tt, lon, spd)


def load_sky() -> Sky:
    """The cached sample grid, rebuilt when it's stale, the ayanamsa changed, or it's missing."""
    now = datetime.now(timezone.utc)
    need_until = tt_of(now.replace(year=now.year + EPHEMERIS_YEARS_AHEAD)) - 30
    if CACHE.exists():
        z = np.load(CACHE)
        if float(z["ayanamsa"]) == ayanamsa_j2000() and float(z["tt"][-1]) >= need_until:
            return Sky(z["tt"], {g: z[f"lon_{g.value}"] for g in GRAHAS}, {g: z[f"spd_{g.value}"] for g in GRAHAS})
    sky = build_sky()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        CACHE,
        tt=sky.tt,
        ayanamsa=ayanamsa_j2000(),
        **{f"lon_{g.value}": sky.lon[g] for g in GRAHAS},
        **{f"spd_{g.value}": sky.spd[g] for g in GRAHAS},
    )
    return sky
