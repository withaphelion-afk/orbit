"""The runner's heartbeat file (data/runner_status.json).

The runner writes it at the start and end of every cycle; the API reads it to
tell whether the 24/7 loop is actually alive, when it last finished a cycle,
whether that cycle worked, and when the next one is due.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from orbit.config.settings import DATA_DIR

STATUS_PATH = DATA_DIR / "runner_status.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_status() -> dict | None:
    if not STATUS_PATH.exists():
        return None
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None  # caught mid-write; the next read will be fine


def _write(status: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, indent=2), encoding="utf-8")
    os.replace(tmp, STATUS_PATH)  # atomic, so readers never see half a file


def mark_started(interval_seconds: int) -> None:
    _write({"pid": os.getpid(), "started_at": _now(), "interval_seconds": interval_seconds, "cycles": 0})


def mark_cycle_start() -> None:
    status = read_status() or {}
    status.update({"last_cycle_started_at": _now(), "in_cycle": True})
    _write(status)


def mark_cycle_end(ok: bool, error: str | None = None) -> None:
    status = read_status() or {}
    finished = datetime.now(timezone.utc)
    status.update(
        {
            "in_cycle": False,
            "last_cycle_finished_at": finished.isoformat(),
            "last_cycle_ok": ok,
            "last_error": error,
            "cycles": int(status.get("cycles", 0)) + 1,
            "next_cycle_at": (finished + timedelta(seconds=int(status.get("interval_seconds", 3600)))).isoformat(),
        }
    )
    _write(status)


def mark_next_analysis(at: datetime) -> None:
    status = read_status() or {}
    if status.get("next_analysis_at") != at.isoformat():
        status["next_analysis_at"] = at.isoformat()
        _write(status)


def mark_analysis(run_id: str, next_at: datetime) -> None:
    status = read_status() or {}
    status.update({"last_scheduled_run_id": run_id, "last_scheduled_run_at": _now(), "next_analysis_at": next_at.isoformat()})
    _write(status)
