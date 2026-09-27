"""One analysis run, as a process: python -m orbit.analysis.run --job <id>

Started by the web "Run analysis" button or the runner's daily schedule (see
jobs.py). Steps: refresh data (optional), compute exact transit moments,
rebuild the playbook (daily + hourly), backtest the strategy, retrain the
feedback loop (calibrate.py) on backtest + live outcomes, re-check the Vedic
model, optionally the placebo check, then record what changed. Progress and log lines go to the run's record file,
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


def _strategy_and_model(rep: Reporter, events, start: float, end: float) -> dict:
    """Backtest, feedback-loop retrain, live refresh, Vedic model. Returns summary fields."""
    from orbit.analysis import model
    from orbit.analysis.series import load_price_series
    from orbit.backtest.engine import run_all
    from orbit.strategy import calibrate, live
    from orbit.vedic.states import build_states

    series = {a: load_price_series(a) for a in ALL_ASSETS}
    rep.step("Backtesting RSI divergence", start)
    bt = run_all(series)["pooled"]
    rep.log(f"Backtest: {bt.get('trades', 0)} trades, win rate {bt.get('win_rate', 0):.1%}, avg {bt.get('avg_r', 0):+.3f}R")
    rep.step("Retraining the feedback loop", start + 0.02)
    cal = calibrate.train()
    oos = cal.get("out_of_sample") or {}
    rep.log(
        f"Feedback loop: {cal['n_backtest']} backtest + {cal['n_live']} live outcomes; "
        + (f"out-of-sample Brier {oos['brier']:.4f} vs {oos['brier_base_rate']:.4f} plain win rate ({'skill' if cal['skill'] else 'no skill: confidence = plain win rate'})" if oos else cal.get("note", ""))
    )
    counts = live.refresh(series)
    rep.log(f"Suggestions: {counts['new']} new, {counts['expired']} expired, {counts['resolved']} outcomes resolved")
    states = build_states(events=events)
    verdicts = {}
    usable = [a for a in ALL_ASSETS if len(series[a]) >= 300]
    for k, asset in enumerate(usable):
        rep.step(f"Vedic model: {asset.value}", start + 0.04 + (end - start - 0.04) * k / max(1, len(usable)))
        res = model.evaluate(asset, series[asset], states)
        verdicts[asset.value] = {k: r["verdict"] for k, r in res["results"].items()}
        skilled = [k for k, v in verdicts[asset.value].items() if v == "adds skill"]
        rep.log(f"Vedic model {asset.value}: " + (f"adds skill on {', '.join(skilled)}" if skilled else "no added skill on any target"))
    return {
        "backtest": {k: bt.get(k) for k in ("trades", "win_rate", "avg_r", "profit_factor", "max_drawdown_r")},
        "calibration_skill": cal["skill"],
        "suggestions": counts,
        "model_verdicts": verdicts,
    }


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
        span = (0.14, 0.40) if run.include_placebo else (0.14, 0.55)
        meta = build_all(progress=lambda step, f: rep.step(step, span[0] + (span[1] - span[0]) * f), events=events)
        rep.log(f"Playbook: {meta.total_tests} tests across {len(meta.tests_by_family)} families")
        summary = {
            "total_tests": meta.total_tests,
            "tests_by_family": meta.tests_by_family,
            "assets": meta.assets,
        }
        summary.update(_strategy_and_model(rep, events, span[1], 0.62 if run.include_placebo else 0.97))
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
