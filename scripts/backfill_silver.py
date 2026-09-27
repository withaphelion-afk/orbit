"""One-time (resumable) download of spot silver history from Dukascopy.

The feed throttles bulk readers hard, so this goes slowly and caches every
file: about 280 monthly files of hourly bars, plus daily files for the current
month. Interrupt it any time and run it again; it continues where it stopped.
When the cache is complete it rebuilds silver's daily and hourly history.

    uv run python scripts/backfill_silver.py
"""

import sys
import time

from orbit.data import dukascopy
from orbit.data.history import rebuild_silver_from_cache, silver_targets

if __name__ == "__main__":
    wanted = silver_targets()
    t0 = time.perf_counter()

    def progress(i: int, n: int, note: str) -> None:
        print(f"[{i}/{n}] {note} ({time.perf_counter() - t0:.0f}s)", flush=True)

    counts = dukascopy.download(wanted, on_progress=progress)
    print(counts, flush=True)
    if counts["remaining"]:
        print("Stopped before finishing; run again to continue.")
        sys.exit(1)
    daily, hourly = rebuild_silver_from_cache()
    print(f"Silver rebuilt from Dukascopy spot: {daily} daily bars, {hourly} hourly bars.")
