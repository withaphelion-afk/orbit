"""The 24/7 loop: on an interval, forever, fetch fresh data, recompute
every feature, and log a snapshot of the current state.

This is deliberately the "thin" layer — it doesn't decide anything or
compute any logic itself, it just wires together data/pipeline.py and
features/pipeline.py on a schedule, and starts the daily analysis run
(analysis/run.py, as its own process) at ANALYSIS_DAILY_AT_UTC. After each
data refresh it also checks the strategy for a new RSI divergence on the
latest completed bar, expires undecided suggestions and resolves outcomes
(strategy/live.py), so the journal and drift check stay current, and once a
day it syncs the shared data with GitHub (datasync.py) so the other machines
can start from it.

Design note for anyone maintaining this: a 24/7 process must never crash
on a single bad cycle (a dropped API call, a rate limit, a network
hiccup). Every cycle is wrapped in try/except so one failure gets logged
and the loop keeps running instead of the whole thing going down.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from orbit import datasync
from orbit.analysis import jobs
from orbit.config.settings import ANALYSIS_DAILY_AT_UTC, ANALYSIS_SCHEDULE_ENABLED, DATA_DIR, PLACEBO_WEEKDAY, RUNNER_INTERVAL_SECONDS
from orbit.core.types import Asset
from orbit.data.pipeline import fetch_all_ephemeris, fetch_all_prices
from orbit.features.pipeline import compute_all_features
from orbit.features.store import load_features
from orbit.runner import schedule, status

LOG_DIR = DATA_DIR / "logs"


def _setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("orbit.runner")
    logger.setLevel(logging.INFO)
    if not logger.handlers:  # avoid duplicate handlers if this gets called more than once
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

        file_handler = logging.FileHandler(LOG_DIR / "runner.log")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger


def _log_current_state(logger: logging.Logger) -> None:
    """A human-readable snapshot of what the system currently sees —
    this is the "watching all the time" output you'd actually check.
    """
    regime_records = load_features(Asset.BTC, "regime")
    if regime_records:
        latest_regime = regime_records[-1]
        regime_name = {1.0: "BULL", -1.0: "BEAR", 0.0: "CHOPPY"}.get(latest_regime.value, "UNKNOWN")
        logger.info(f"Regime as of {latest_regime.date.date()}: {regime_name}")
    else:
        logger.info("No regime data available yet.")


def run_once(logger: logging.Logger) -> None:
    logger.info("Cycle starting: fetching prices + ephemeris, recomputing features...")
    fetch_all_prices()
    fetch_all_ephemeris()
    compute_all_features()
    from orbit.strategy import divergence_model, live

    model = divergence_model.train()  # find candidates on 1H/4H/1D/1W, retrain on everything graded + your labels, score
    logger.info(f"Divergence model: {model['n_market']} graded + {model['n_user']} of yours; {'trusted' if model['trusted'] else 'unproven'}.")
    counts = live.refresh()
    if any(counts.values()):
        logger.info(f"Suggestions: {counts['new']} new, {counts['expired']} expired, {counts['resolved']} outcomes resolved.")
    _log_current_state(logger)
    logger.info("Cycle complete.")


def _maybe_sync(logger: logging.Logger) -> None:
    """Once a day, share this machine's data on GitHub and take the other machines'."""
    if not datasync.DATA_SYNC_ENABLED or not datasync.due():
        return
    try:
        result = datasync.sync()
        (logger.warning if result.warning else logger.info)(result.summary())
    except Exception as exc:
        logger.warning(f"Data sync failed ({type(exc).__name__}: {exc}); will try again in {datasync.RETRY_HOURS_AFTER_ERROR} hours.")


def _maybe_start_analysis(logger: logging.Logger, now: datetime, at, last_cycle_started: datetime | None) -> tuple[bool, datetime]:
    """Start the scheduled analysis if it's due. Returns (needs a data cycle first, next slot)."""
    active = jobs.current()
    last = jobs.last_successful()
    slot_start = schedule.latest_slot(now, at)
    failed = [r.finished_at for r in jobs.list_runs(10) if r.trigger == "schedule" and r.created_at >= slot_start and r.status == "failed" and r.finished_at]
    decision = schedule.analysis_decision(now, at, PLACEBO_WEEKDAY, last.started_at if last else None, active is not None, failed)
    if not decision.due:
        return False, decision.next_at
    if last_cycle_started is None or last_cycle_started < decision.slot:
        return True, decision.next_at  # refresh data (the new daily bar) before analysing it
    try:
        run = jobs.start("schedule", include_placebo=decision.include_placebo, refresh_data=False)
        logger.info(f"Scheduled analysis started: run {run.id}{' with placebo check' if decision.include_placebo else ''}.")
        status.mark_analysis(run.id, decision.next_at)
    except jobs.AlreadyRunning as exc:
        logger.info(f"Scheduled analysis skipped: run {exc.run.id} is already in progress.")
    return False, decision.next_at


def run_forever(interval_seconds: int = RUNNER_INTERVAL_SECONDS, schedule_analysis: bool = ANALYSIS_SCHEDULE_ENABLED) -> None:
    logger = _setup_logging()
    at = schedule.parse_hhmm(ANALYSIS_DAILY_AT_UTC)
    logger.info(
        f"Orbit runner starting. Cycle interval: {interval_seconds}s. "
        + (f"Daily analysis at {ANALYSIS_DAILY_AT_UTC} UTC." if schedule_analysis else "Scheduled analysis off.")
    )
    status.mark_started(interval_seconds)
    next_data = datetime.now(timezone.utc)
    next_analysis = next_data + timedelta(days=1)
    last_cycle_started: datetime | None = None

    while True:
        now = datetime.now(timezone.utc)
        if now >= next_data:
            last_cycle_started = now
            status.mark_cycle_start()
            try:
                run_once(logger)
                status.mark_cycle_end(ok=True)
            except Exception as exc:
                # Swallow and log — a bad cycle (network blip, rate limit, ...)
                # must never take down a process meant to run 24/7.
                logger.exception("Cycle failed, will retry next interval.")
                status.mark_cycle_end(ok=False, error=f"{type(exc).__name__}: {exc}")
            # Even after a failed cycle: a machine whose venue is blocked can still take the other machines' bars.
            _maybe_sync(logger)
            next_data = datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)

        if schedule_analysis:
            try:
                needs_data, next_analysis = _maybe_start_analysis(logger, datetime.now(timezone.utc), at, last_cycle_started)
                status.mark_next_analysis(next_analysis)
                if needs_data:
                    next_data = datetime.now(timezone.utc)
                    continue
            except Exception:
                logger.exception("Could not check or start the scheduled analysis.")

        time.sleep(schedule.seconds_until_next_wake(datetime.now(timezone.utc), next_data, next_analysis if schedule_analysis else next_data))


def run_single_cycle(interval_seconds: int = RUNNER_INTERVAL_SECONDS) -> bool:
    """One data cycle, then exit: for hosts that start the runner on a schedule
    (GitHub Actions) instead of keeping it alive. The scheduled analysis is a
    separate job there, and syncing is the caller's job. Returns whether it worked."""
    logger = _setup_logging()
    status.mark_scheduled(interval_seconds)
    status.mark_next_analysis(schedule.next_slot(datetime.now(timezone.utc), schedule.parse_hhmm(ANALYSIS_DAILY_AT_UTC)))
    status.mark_cycle_start()
    try:
        run_once(logger)
        status.mark_cycle_end(ok=True)
        return True
    except Exception as exc:
        logger.exception("Cycle failed.")
        status.mark_cycle_end(ok=False, error=f"{type(exc).__name__}: {exc}")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Orbit's 24/7 runner")
    parser.add_argument("--once", action="store_true", help="run one data cycle and exit (scheduled hosts)")
    if parser.parse_args().once:
        raise SystemExit(0 if run_single_cycle() else 1)
    run_forever()
