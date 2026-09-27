"""Sanity check for the whole playbook pipeline: run it on fake calendars.

Every transit (and its exact moment) is moved by an arbitrary offset, so no
real astronomy lines up with prices any more, and the full per-asset analysis
is re-run: outcomes, circular-shift tests, FDR, labels, daily and hourly. Any
"moderate" or "strong" result on a placebo calendar is a false discovery by
construction. With no real effects they should be rare; if they turn up
often, the method is over-confident and the real playbook shouldn't be
trusted until it's fixed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable

from orbit.config.settings import INCLUDE_MOON
from orbit.core.types import TransitEvent
from orbit.analysis.exact_times import shift
from orbit.analysis.patterns import build_patterns
from orbit.analysis.playbook import ALL_ASSETS, ANALYSIS_DIR, build_asset_playbook, load_events
from orbit.analysis.series import load_planet_series, load_price_series

OFFSETS_DAYS = [97, 211, 389, 577, 733, 1009, 1291, 1597]
DISCOVERY = ("moderate", "strong")


def run_placebo(progress: Callable[[str, float], None] | None = None, events: list[TransitEvent] | None = None) -> dict:
    say = progress or (lambda step, frac: None)
    now = datetime.now(timezone.utc)
    planets = load_planet_series()
    real = events if events is not None else load_events()
    daily = {a: load_price_series(a) for a in ALL_ASSETS}
    hourly = {a: load_price_series(a, timeframe="1h") for a in ALL_ASSETS}
    runs = []
    for k, offset in enumerate(OFFSETS_DAYS):
        say(f"Placebo calendar {k + 1} of {len(OFFSETS_DAYS)} (shifted {offset} days)", k / len(OFFSETS_DAYS))
        shifted = shift(real, offset)
        patterns = build_patterns(shifted, INCLUDE_MOON)
        row = {"offset_days": offset}
        for asset in ALL_ASSETS:
            if len(daily[asset]) < 300:
                continue
            pb, counts = build_asset_playbook(asset, daily[asset], patterns, shifted, planets, now, hourly[asset] if len(hourly[asset]) else None)
            row[asset.value] = {
                "tests": sum(counts.values()),
                "discoveries": [r.pattern_id for r in pb.patterns if r.label.value in DISCOVERY],
                "timing_discoveries": [r.pattern_id for r in pb.patterns if r.timing_label.value in DISCOVERY],
            }
        runs.append(row)
    asset_runs = [r[a.value] for r in runs for a in ALL_ASSETS if a.value in r]
    summary = {
        "checked_at": now.isoformat(),
        "placebo_runs": len(asset_runs),
        "runs_with_any_discovery": sum(1 for r in asset_runs if r["discoveries"]),
        "total_false_discoveries": sum(len(r["discoveries"]) for r in asset_runs),
        "runs_with_any_timing_discovery": sum(1 for r in asset_runs if r["timing_discoveries"]),
        "total_false_timing_discoveries": sum(len(r["timing_discoveries"]) for r in asset_runs),
        "runs": runs,
    }
    (ANALYSIS_DIR / "placebo.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    say("Placebo check written", 1.0)
    return summary
