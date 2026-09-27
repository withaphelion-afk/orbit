"""Manual script: build the Vedic sky (sidereal positions of the 9 grahas every
6 hours, 2000 to two years ahead) and every Vedic event on it. Cached under
data/vedic/; later runs only rebuild when the cache no longer reaches far
enough ahead.

Run it with:
    uv run python scripts/fetch_ephemeris.py
"""

from orbit.data.pipeline import fetch_all_ephemeris

if __name__ == "__main__":
    n = fetch_all_ephemeris()
    print(f"Vedic sky ready: {n:,} events from 2000 to two years ahead.")
