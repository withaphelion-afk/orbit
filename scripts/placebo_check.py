"""Sanity check for the whole playbook pipeline: run it on fake calendars.

Every transit date is moved by an arbitrary offset (so no real astronomy
lines up with prices any more), and the full per-asset analysis is re-run:
outcomes, circular-shift tests, FDR, labels. Any "moderate" or "strong"
result on a placebo calendar is a false discovery by construction.

With Benjamini-Hochberg at q = 0.05/0.10 and no real effects, discoveries on
placebo runs should be rare. If they turn up often, the method is
over-confident and the real playbook shouldn't be trusted until it's fixed.

Writes data/analysis/placebo.json. Run after build_playbook.py:
    uv run python scripts/placebo_check.py
"""

import json
from datetime import datetime, timedelta, timezone

from orbit.analysis.patterns import build_patterns
from orbit.analysis.playbook import ALL_ASSETS, ANALYSIS_DIR, build_asset_playbook
from orbit.analysis.series import load_planet_series, load_price_series
from orbit.analysis.transit_events import detect_all
from orbit.config.settings import INCLUDE_MOON

OFFSETS_DAYS = [97, 211, 389, 577, 733, 1009, 1291, 1597]

if __name__ == "__main__":
    now = datetime.now(timezone.utc)
    planets = load_planet_series()
    real = detect_all(planets)
    series = {a: load_price_series(a) for a in ALL_ASSETS}
    runs = []
    for offset in OFFSETS_DAYS:
        shifted = [e.model_copy(update={"date": e.date + timedelta(days=offset)}) for e in real]
        patterns = build_patterns(shifted, INCLUDE_MOON)
        row = {"offset_days": offset}
        for asset in ALL_ASSETS:
            pb, counts = build_asset_playbook(asset, series[asset], patterns, shifted, planets, now)
            found = [r.pattern_id for r in pb.patterns if r.label.value in ("moderate", "strong")]
            row[asset.value] = {"tests": sum(counts.values()), "discoveries": found}
        runs.append(row)
        print(offset, {a.value: len(row[a.value]["discoveries"]) for a in ALL_ASSETS})
    total = sum(len(r[a.value]["discoveries"]) for r in runs for a in ALL_ASSETS)
    runs_with_any = sum(1 for r in runs for a in ALL_ASSETS if r[a.value]["discoveries"])
    summary = {
        "checked_at": now.isoformat(),
        "placebo_runs": len(OFFSETS_DAYS) * len(ALL_ASSETS),
        "runs_with_any_discovery": runs_with_any,
        "total_false_discoveries": total,
        "runs": runs,
    }
    (ANALYSIS_DIR / "placebo.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"{runs_with_any} of {summary['placebo_runs']} placebo asset-runs produced a moderate/strong result ({total} in total).")
