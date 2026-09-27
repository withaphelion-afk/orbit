"""The 24/7 loop: on an interval, forever, fetch fresh data, recompute
every feature, and log a snapshot of the current state.

This is deliberately the "thin" layer — it doesn't decide anything or
compute any logic itself, it just wires together data/pipeline.py and
features/pipeline.py on a schedule. No trade suggestions happen here yet
(that's the strategy layer, still to come) — right now this is purely
the "always watching, always logging" backbone.

Design note for anyone maintaining this: a 24/7 process must never crash
on a single bad cycle (a dropped API call, a rate limit, a network
hiccup). Every cycle is wrapped in try/except so one failure gets logged
and the loop keeps running instead of the whole thing going down.
"""

from __future__ import annotations

import logging
import time

from orbit.config.settings import DATA_DIR, RUNNER_INTERVAL_SECONDS
from orbit.core.types import Asset
from orbit.data.pipeline import fetch_all_ephemeris, fetch_all_prices
from orbit.features.pipeline import compute_all_features
from orbit.features.store import load_features

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
    _log_current_state(logger)
    logger.info("Cycle complete.")


def run_forever(interval_seconds: int = RUNNER_INTERVAL_SECONDS) -> None:
    logger = _setup_logging()
    logger.info(f"Orbit runner starting. Cycle interval: {interval_seconds}s")

    while True:
        try:
            run_once(logger)
        except Exception:
            # Swallow and log — a bad cycle (network blip, rate limit, ...)
            # must never take down a process meant to run 24/7.
            logger.exception("Cycle failed, will retry next interval.")

        time.sleep(interval_seconds)


if __name__ == "__main__":
    run_forever()
