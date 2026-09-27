"""Periodic job: rebuild the transit playbook for every asset.

Heavy compared with the runner (every pattern x horizon tested against every
circular shift), and it only changes when new bars or ephemeris arrive, so it
runs on its own schedule (daily or weekly), never inside the hourly loop.

Run scripts/fetch_data.py and scripts/fetch_ephemeris.py first. Then:
    uv run python scripts/build_playbook.py
"""

import time

from orbit.analysis.playbook import build_all

if __name__ == "__main__":
    started = time.perf_counter()
    meta = build_all()
    print(f"Playbook built in {time.perf_counter() - started:.1f}s, {meta.total_tests} tests across {len(meta.tests_by_family)} families.")
    for asset, info in meta.assets.items():
        labels = ", ".join(f"{k.removeprefix('patterns_')}: {v}" for k, v in info.items() if k.startswith("patterns_"))
        print(f"  {asset}: {info.get('history_start')} -> {info.get('history_end')} ({info.get('bars')} bars)  {labels}")
