"""Sanity check for the whole playbook pipeline: run it on fake calendars
(see orbit/analysis/placebo.py). Writes data/analysis/placebo.json.

Run after build_playbook.py:
    uv run python scripts/placebo_check.py
"""

from orbit.analysis.placebo import run_placebo

if __name__ == "__main__":
    s = run_placebo(progress=lambda step, f: print(step, flush=True))
    print(
        f"{s['runs_with_any_discovery']} of {s['placebo_runs']} placebo asset-runs produced a moderate/strong daily result "
        f"({s['total_false_discoveries']} in total); {s['runs_with_any_timing_discovery']} produced one in the hourly timing "
        f"({s['total_false_timing_discoveries']} in total)."
    )
