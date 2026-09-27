"""Builds SystemStatus and AlertLog from the runner's log file and the
current state of stored data — an honest read of what's actually running,
not a hardcoded "everything's fine."
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from orbit.api.schemas import AlertLog, FeedStatus, SystemStatus
from orbit.config.settings import RUNNER_INTERVAL_SECONDS, TIMEFRAME, TRACKED_ASSETS
from orbit.core.types import Asset
from orbit.data.storage import load_candles
from orbit.runner.loop import LOG_DIR

LOG_PATH = LOG_DIR / "runner.log"
LOG_LINE = re.compile(r"^(?P<ts>\S+ \S+),\d+ \[(?P<level>\w+)\] (?P<message>.*)$")


def _parse_log_lines(limit: int = 10) -> list[AlertLog]:
    if not LOG_PATH.exists():
        return []

    lines = LOG_PATH.read_text().strip().splitlines()[-limit:]
    alerts = []
    for line in lines:
        match = LOG_LINE.match(line)
        if not match:
            continue
        level = match.group("level")
        mapped_level = {"INFO": "INFO", "WARNING": "WARN", "ERROR": "ALERT"}.get(level, "INFO")
        try:
            timestamp = datetime.strptime(match.group("ts"), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        alerts.append(AlertLog(timestamp=timestamp, level=mapped_level, message=match.group("message")))
    return alerts


def _last_cycle_time(alerts: list[AlertLog]) -> datetime | None:
    for alert in reversed(alerts):
        if "Cycle complete" in alert.message:
            return alert.timestamp
    return None


def build_system_status() -> SystemStatus:
    alerts = _parse_log_lines(limit=20)
    last_eval = _last_cycle_time(alerts)

    if last_eval is None:
        runner_state = "DOWN"
    elif datetime.now(timezone.utc) - last_eval > timedelta(seconds=RUNNER_INTERVAL_SECONDS * 2):
        runner_state = "STALE"
    else:
        runner_state = "LIVE"

    feeds = []
    for asset_name in TRACKED_ASSETS:
        asset = Asset(asset_name)
        candles = load_candles(asset, TIMEFRAME)
        if candles:
            feeds.append(FeedStatus(asset=asset, source="LIVE", last_bar=candles[-1].timestamp))

    next_eval = last_eval + timedelta(seconds=RUNNER_INTERVAL_SECONDS) if last_eval else None

    return SystemStatus(
        runner=runner_state,
        strategy="none yet — data collection and feature research only",
        timeframe=TIMEFRAME,
        auto_execution=False,
        last_eval=last_eval,
        next_eval=next_eval,
        feeds=feeds,
        alerts=alerts[-10:],
        config={
            "assets": ", ".join(TRACKED_ASSETS),
            "timeframe": TIMEFRAME,
            "runner_interval_seconds": str(RUNNER_INTERVAL_SECONDS),
        },
    )
