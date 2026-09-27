"""Daily planetary positions (zodiac sign + retrograde status) via Skyfield.

Skyfield computes real astronomical positions using NASA JPL ephemeris
data (downloaded once as de421.bsp, then cached locally). We convert each
planet's ecliptic longitude into a zodiac sign, since that's the unit
astrology-based analysis usually reasons in (e.g. "Jupiter in Leo").

Retrograde is detected by comparing a planet's longitude today vs.
yesterday: if it moved backward (accounting for the 0/360 wraparound),
it's retrograde from Earth's point of view. This is an appearance, not
the planet literally reversing — but it's the standard astrological
convention.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from skyfield.api import Loader

from orbit.config.settings import DATA_DIR
from orbit.core.types import EphemerisSnapshot, Planet
from orbit.data.dates import utc_day

# Skyfield downloads its ephemeris kernel (de421.bsp, ~17MB, NASA JPL data)
# once and reuses it after that. It's a generated cache file, not source —
# stored under data/ alongside everything else gitignored, not the repo root.
_loader = Loader(DATA_DIR / "ephemeris_cache")

ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# Skyfield/JPL body names for each planet we track. The Sun and Moon are
# included because astrology treats them as "planets" too.
BODY_NAMES = {
    Planet.SUN: "sun",
    Planet.MOON: "moon",
    Planet.MERCURY: "mercury barycenter",
    Planet.VENUS: "venus barycenter",
    Planet.MARS: "mars barycenter",
    Planet.JUPITER: "jupiter barycenter",
    Planet.SATURN: "saturn barycenter",
    Planet.URANUS: "uranus barycenter",
    Planet.NEPTUNE: "neptune barycenter",
    Planet.PLUTO: "pluto barycenter",
}

_ephemeris = None  # lazily loaded — downloads de421.bsp once, then reuses the local file
_timescale = None


def _get_ephemeris():
    global _ephemeris, _timescale
    if _ephemeris is None:
        _ephemeris = _loader("de421.bsp")
        _timescale = _loader.timescale()
    return _ephemeris, _timescale


def longitude_to_sign(longitude: float) -> str:
    """Ecliptic longitude (0-360 degrees) -> zodiac sign name."""
    index = int(longitude % 360 // 30)
    return ZODIAC_SIGNS[index]


def _ecliptic_longitude(eph, ts, planet: Planet, date: datetime) -> float:
    earth = eph["earth"]
    body = eph[BODY_NAMES[planet]]
    t = ts.utc(date.year, date.month, date.day)
    _, lon, _ = earth.at(t).observe(body).apparent().ecliptic_latlon()
    return lon.degrees


def compute_snapshot(planet: Planet, date: datetime) -> EphemerisSnapshot:
    """Position + retrograde status for one planet on one date."""
    eph, ts = _get_ephemeris()

    longitude_today = _ecliptic_longitude(eph, ts, planet, date)
    longitude_yesterday = _ecliptic_longitude(eph, ts, planet, date - timedelta(days=1))

    delta = (longitude_today - longitude_yesterday + 540) % 360 - 180  # wraparound-safe difference
    retrograde = delta < 0

    return EphemerisSnapshot(
        planet=planet,
        date=date,
        longitude=longitude_today,
        sign=longitude_to_sign(longitude_today),
        retrograde=retrograde,
    )


def compute_all_snapshots(date: datetime) -> list[EphemerisSnapshot]:
    """Position + retrograde status for every tracked planet, on one date."""
    return [compute_snapshot(planet, date) for planet in BODY_NAMES]


def backfill_planet(planet: Planet, start_date: datetime, days: int) -> list[EphemerisSnapshot]:
    """Position + retrograde status for `planet` across `days` days starting
    at `start_date`, computed as one vectorized batch instead of looping
    day-by-day — this is what makes fetching years of history practical.
    """
    eph, ts = _get_ephemeris()
    earth = eph["earth"]
    body = eph[BODY_NAMES[planet]]
    # Positions are computed at 00:00 UTC, so date each snapshot at midnight UTC
    # too; that is what prices and features are keyed by (see data/dates.py).
    start_date = utc_day(start_date)

    # Requesting one extra day *before* the range lets us compute retrograde
    # for the first day too, via the same backward-difference as compute_snapshot.
    day_numbers = [start_date.day + offset for offset in range(-1, days)]
    t = ts.utc(start_date.year, start_date.month, day_numbers)
    _, lon, _ = earth.at(t).observe(body).apparent().ecliptic_latlon()
    longitudes = lon.degrees

    snapshots = []
    for i in range(1, days + 1):  # skip index 0, which is the lookback-only day
        delta = (longitudes[i] - longitudes[i - 1] + 540) % 360 - 180
        date = start_date + timedelta(days=i - 1)
        snapshots.append(
            EphemerisSnapshot(
                planet=planet,
                date=date,
                longitude=longitudes[i],
                sign=longitude_to_sign(longitudes[i]),
                retrograde=delta < 0,
            )
        )
    return snapshots
