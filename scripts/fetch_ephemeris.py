"""Manual script: backfill years of planetary position history for all
tracked planets.

Run it with:
    uv run python scripts/fetch_ephemeris.py
"""

from orbit.data.pipeline import EPHEMERIS_YEARS_OF_HISTORY, fetch_all_ephemeris

if __name__ == "__main__":
    fetch_all_ephemeris()
    print(f"Backfilled {EPHEMERIS_YEARS_OF_HISTORY} years of ephemeris data for all planets.")
