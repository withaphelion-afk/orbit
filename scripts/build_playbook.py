"""Rebuild the transit playbook for every asset, daily and hourly.

The same run the web "Run analysis" button and the runner's 00:30 UTC
schedule start (those go through orbit.analysis.jobs so only one runs at a
time); this script runs it directly in the foreground.

Run scripts/fetch_data.py and scripts/fetch_ephemeris.py first. Then:
    uv run python scripts/build_playbook.py
"""

import time

from orbit.analysis.playbook import build_all

if __name__ == "__main__":
    started = time.perf_counter()
    meta = build_all(progress=lambda step, f: print(f"[{f:4.0%}] {step}", flush=True))
    print(f"Playbook built in {time.perf_counter() - started:.1f}s, {meta.total_tests} tests across {len(meta.tests_by_family)} families.")
    for asset, info in meta.assets.items():
        daily = ", ".join(f"{k.removeprefix('patterns_')}: {v}" for k, v in info.items() if k.startswith("patterns_"))
        timing = ", ".join(f"{k.removeprefix('timing_')}: {v}" for k, v in info.items() if k.startswith("timing_"))
        print(f"  {asset}: {info.get('history_start')} -> {info.get('history_end')} ({info.get('bars')} daily, {info.get('hourly_bars')} hourly bars)")
        print(f"      daily  {daily}")
        if timing:
            print(f"      hourly {timing}")
