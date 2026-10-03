"""One analysis run, as a process: python -m orbit.analysis.run --job <id>

Started by the web "Run analysis" button or the runner's daily schedule (see
jobs.py). Steps: refresh data (optional), compute exact transit moments,
rebuild the playbook (daily + hourly), record upcoming projections and grade
elapsed ones (projection_log.py), backtest the strategy, retrain the
divergence model (strategy/divergence_model.py) with its walk-forward check, re-check the Vedic
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


def _projections(rep: Reporter, events, built: list[Asset]) -> dict:
    """Record this run's projections in the forward track record and grade the ones
    whose windows have closed. Returns summary fields."""
    from datetime import datetime, timezone

    from orbit.core.types import AssetPlaybook
    from orbit.analysis import projection_log
    from orbit.analysis.exceptions import regime_per_bar
    from orbit.analysis.playbook import _regime_context
    from orbit.analysis.projections import build_projections, current_conditions
    from orbit.analysis.series import load_price_series

    now = datetime.now(timezone.utc)
    playbooks, conditions = {}, {}
    for asset in built:
        path = ANALYSIS_DIR / f"{asset.value}.json"
        if not path.exists():
            continue
        playbooks[asset] = AssetPlaybook.model_validate_json(path.read_text(encoding="utf-8"))
        series = load_price_series(asset)
        regimes = regime_per_bar(series, _regime_context(asset, series)[0]) if len(series) else []
        conditions[asset] = current_conditions(series, next((r for r in reversed(regimes) if r), None))
    rows = build_projections(events, playbooks, now, conditions=conditions)
    added = projection_log.record(rows, now)
    graded = projection_log.grade(now)
    hits = sum(1 for r in graded if r.hit)
    scored = sum(1 for r in graded if r.hit is not None)
    rep.log(f"Projections: {len(rows)} in the next 60 days, {added} newly recorded; {scored} graded this run ({hits} hits)")
    return {"upcoming": len(rows), "recorded": added, "graded": scored, "hits": hits}


def _strategy_and_model(rep: Reporter, events, start: float, end: float) -> dict:
    """Backtest, feedback-loop retrain, live refresh, Vedic model. Returns summary fields."""
    from orbit.analysis import model
    from orbit.analysis.series import load_price_series
    from orbit.backtest.engine import run_all
    from orbit.strategy import divergence_model, live
    from orbit.vedic.states import build_states

    series = {a: load_price_series(a) for a in ALL_ASSETS}
    rep.step("Training the divergence model (1H, 4H, 1D, 1W)", start)
    rows = divergence_model.build()
    cal = divergence_model.train(rows)
    oos = cal.get("out_of_sample") or {}
    rep.log(
        f"Divergence model: {cal['n_market']} graded + {cal['n_user']} of yours; "
        + (f"out-of-sample Brier {oos['brier']:.4f} vs {oos['brier_base_rate']:.4f} plain rate ({'trusted' if cal['trusted'] else 'unproven'})" if oos else cal.get("note", ""))
    )
    rep.step("Backtesting the divergence strategy (4H, 1D)", start + 0.02)
    report = run_all(cal, rows)
    for tf, r in report["timeframes"].items():
        bt = r["pooled"]
        rep.log(f"Backtest {tf}: {bt.get('trades', 0)} trades, win rate {bt.get('win_rate', 0):.1%}, avg {bt.get('avg_r', 0):+.3f}R")
    bt = report["pooled"]
    counts = live.refresh()
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
        "calibration_skill": cal["trusted"],
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
        rep.step("Recording and grading projections", span[1])
        try:
            built = [a for a in ALL_ASSETS if "skipped" not in meta.assets.get(a.value, {"skipped": True})]
            summary["projections"] = _projections(rep, events, built)
        except Exception as exc:
            # The track record is a side product: losing one day of it must not lose the run.
            rep.log(f"Projections skipped this run: {type(exc).__name__}: {exc}")
            rep.log(traceback.format_exc())
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


def run_now(trigger: str, include_placebo: bool, refresh_data: bool, run_id: str | None = None) -> None:
    """Create a run and execute it in this process (for hosts without a long-lived
    runner, e.g. a scheduled GitHub Actions job). Same record as a button-started run."""
    from orbit.analysis import jobs

    run = jobs.start(trigger, include_placebo=include_placebo, refresh_data=refresh_data, spawn=lambda run: None, run_id=run_id)
    if run.status == "failed":
        raise SystemExit(f"could not start analysis run: {run.error}")
    main(run.id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run one Orbit analysis job")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--job", help="run id created by orbit.analysis.jobs.start")
    group.add_argument("--now", action="store_true", help="create a run and execute it here, in the foreground")
    parser.add_argument("--trigger", choices=["manual", "schedule"], default="schedule")
    parser.add_argument("--placebo", action="store_true", help="also run the placebo check (--now only)")
    parser.add_argument("--no-refresh", action="store_true", help="skip refreshing prices and ephemeris (--now only)")
    parser.add_argument("--run-id", help="use this id for the run record (--now only; the web server picks it when it hands a run to GitHub)")
    args = parser.parse_args()
    if args.now:
        run_now(args.trigger, args.placebo, not args.no_refresh, args.run_id)
    else:
        main(args.job)
