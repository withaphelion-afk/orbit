"""One analysis run, as a process: python -m orbit.analysis.run --job <id>

Started by the web "Run analysis" button or the runner's daily schedule (see
jobs.py). Steps: refresh data (optional), compute exact transit moments,
rebuild the playbook (daily + hourly), optionally the placebo check, then
record what changed. Progress and log lines go to the run's record file,
which the API serves to the UI.
"""

from __future__ import annotations

import argparse
import json
import traceback

from orbit.core.types import Asset
from orbit.analysis.jobs import LabelChange, Reporter
from orbit.analysis.playbook import ALL_ASSETS, ANALYSIS_DIR, build_all, load_events


def _labels(asset: Asset) -> dict[str, tuple[str, str, str]]:
    """{pattern_id: (description, daily label, timing label)} from the stored playbook."""
    path = ANALYSIS_DIR / f"{asset.value}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {p["pattern_id"]: (p["description"], p["label"], p.get("timing_label", "insufficient_data")) for p in data["patterns"]}


def _changes(before: dict[Asset, dict], after: dict[Asset, dict]) -> list[LabelChange]:
    out = []
    for asset, now in after.items():
        was = before.get(asset, {})
        for pid, (desc, daily, timing) in now.items():
            old = was.get(pid)
            if old is None or old[1] != daily:
                out.append(LabelChange(asset=asset.value, pattern_id=pid, description=desc, kind="daily", before=old[1] if old else None, after=daily))
            if old is None or old[2] != timing:
                out.append(LabelChange(asset=asset.value, pattern_id=pid, description=desc, kind="timing", before=old[2] if old else None, after=timing))
    # First run: everything is "new", which isn't worth listing.
    return [c for c in out if c.before is not None]


def main(job_id: str) -> None:
    rep = Reporter(job_id)
    run = rep.run
    try:
        before = {a: _labels(a) for a in ALL_ASSETS}
        if run.refresh_data:
            from orbit.data.pipeline import fetch_all_ephemeris, fetch_all_prices

            rep.step("Refreshing prices (daily and hourly)", 0.02)
            fetch_all_prices()
            rep.step("Refreshing ephemeris", 0.08)
            fetch_all_ephemeris()
        rep.step("Computing exact transit moments", 0.12)
        events = load_events()
        span = (0.14, 0.62) if run.include_placebo else (0.14, 0.96)
        meta = build_all(progress=lambda step, f: rep.step(step, span[0] + (span[1] - span[0]) * f), events=events)
        rep.log(f"Playbook: {meta.total_tests} tests across {len(meta.tests_by_family)} families")
        summary = {
            "total_tests": meta.total_tests,
            "tests_by_family": meta.tests_by_family,
            "assets": meta.assets,
        }
        if run.include_placebo:
            from orbit.analysis.placebo import run_placebo

            placebo = run_placebo(progress=lambda step, f: rep.step(step, 0.62 + 0.34 * f), events=events)
            summary["placebo"] = {k: v for k, v in placebo.items() if k != "runs"}
            rep.log(
                f"Placebo: {placebo['runs_with_any_discovery']}/{placebo['placebo_runs']} runs with a false daily discovery, "
                f"{placebo['runs_with_any_timing_discovery']}/{placebo['placebo_runs']} with a false timing discovery"
            )
        changes = _changes(before, {a: _labels(a) for a in ALL_ASSETS})
        rep.log(f"{len(changes)} label changes since the previous run")
        rep.finish(True, summary=summary, changes=changes)
    except Exception as exc:
        rep.log(traceback.format_exc())
        rep.finish(False, error=f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run one Orbit analysis job")
    parser.add_argument("--job", required=True, help="run id created by orbit.analysis.jobs.start")
    main(parser.parse_args().job)
