"""Manual script: backfill years of planetary position history for all
tracked planets.

Run it with:
    uv run python scripts/fetch_ephemeris.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from orbit.core.types import Planet
from orbit.data.ephemeris import backfill_planet
from orbit.data.storage import save_ephemeris_snapshots

# de421.bsp (the ephemeris file we use) is valid 1899-2053, so we can safely
# go back further than crypto/silver price history exists for — this matters
# for slow-moving planets like Jupiter/Saturn, where a useful sample size
# needs several full cycles (Jupiter ~12 years, Saturn ~29 years).
YEARS_OF_HISTORY = 60
DAYS = YEARS_OF_HISTORY * 365

if __name__ == "__main__":
    start_date = datetime.now(timezone.utc) - timedelta(days=DAYS)

    for planet in Planet:
        snapshots = backfill_planet(planet, start_date, days=DAYS)
        path = save_ephemeris_snapshots(snapshots)
        print(f"{planet.value}: saved {len(snapshots)} days -> {path}")
