"""Analysis runs as background jobs, shared by the web "Run analysis" button
and the runner's daily schedule.

A run is a separate process (python -m orbit.analysis.run), so a heavy run
never blocks the API or the runner. Each run has a record file under
data/analysis/runs/{id}.json that the running process keeps updating
(step, progress, log, heartbeat) and that anyone can read.

Only one run at a time: data/analysis/run.lock names the active run. A lock
whose run hasn't sent a heartbeat for HEARTBEAT_STALE_SECONDS is treated as
abandoned (the process crashed or the machine slept) and can be taken over.
Liveness is judged by heartbeat, not by process id, because probing a process
id isn't safe on Windows.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from orbit.config.settings import DATA_DIR, REPO_ROOT

ANALYSIS_DIR = DATA_DIR / "analysis"
RUNS_DIR = ANALYSIS_DIR / "runs"
LOCK_PATH = ANALYSIS_DIR / "run.lock"
HEARTBEAT_SECONDS = 5
HEARTBEAT_STALE_SECONDS = 120
LOG_LINES_KEPT = 300

Status = Literal["queued", "running", "succeeded", "failed"]
Trigger = Literal["manual", "schedule"]


class LabelChange(BaseModel):
    asset: str
    pattern_id: str
    description: str
    kind: Literal["daily", "timing"]
    before: str | None
    after: str


class AnalysisRun(BaseModel):
    id: str
    trigger: Trigger
    include_placebo: bool
    refresh_data: bool
    status: Status
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    step: str = "queued"
    progress: float = 0.0  # 0-1 across the whole run
    log: list[str] = []
    summary: dict = {}
    changes: list[LabelChange] = []
    error: str | None = None


class AlreadyRunning(RuntimeError):
    def __init__(self, run: AnalysisRun):
        super().__init__(f"analysis run {run.id} is already {run.status}")
        self.run = run


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def save(run: AnalysisRun) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path(run.id).with_suffix(".tmp")
    tmp.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, _path(run.id))


def load(run_id: str) -> AnalysisRun | None:
    path = _path(run_id)
    if not path.exists():
        return None
    try:
        return AnalysisRun.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return None  # caught mid-write


def list_runs(limit: int = 20) -> list[AnalysisRun]:
    if not RUNS_DIR.exists():
        return []
    runs = [load(p.stem) for p in sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[: limit * 2]]
    runs = [r for r in runs if r]
    return sorted(runs, key=lambda r: r.created_at, reverse=True)[:limit]


def is_alive(run: AnalysisRun) -> bool:
    if run.status not in ("queued", "running"):
        return False
    beat = run.heartbeat_at or run.created_at
    return _now() - beat < timedelta(seconds=HEARTBEAT_STALE_SECONDS)


def current() -> AnalysisRun | None:
    """The active run, if any. Clears a lock left behind by a run that died."""
    if not LOCK_PATH.exists():
        return None
    run = load(LOCK_PATH.read_text(encoding="utf-8").strip())
    if run and is_alive(run):
        return run
    if run and run.status in ("queued", "running"):
        run.status = "failed"
        run.error = "The run stopped sending heartbeats (process ended or the machine slept)."
        run.finished_at = _now()
        save(run)
    LOCK_PATH.unlink(missing_ok=True)
    return None


def last_successful(trigger: Trigger | None = None) -> AnalysisRun | None:
    for run in list_runs(50):
        if run.status == "succeeded" and (trigger is None or run.trigger == trigger):
            return run
    return None


def _spawn(run: AnalysisRun) -> None:
    args = [sys.executable, "-m", "orbit.analysis.run", "--job", run.id]
    kwargs: dict = {"cwd": str(REPO_ROOT), "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    # The child gets its own copy of the log handle; the parent's is closed straight away.
    with open(RUNS_DIR / f"{run.id}.log", "w", encoding="utf-8") as log:
        subprocess.Popen(args, stdout=log, **kwargs)


def new_run_id() -> str:
    return f"{_now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


def start(trigger: Trigger, include_placebo: bool = False, refresh_data: bool = True, spawn=_spawn, run_id: str | None = None) -> AnalysisRun:
    """Queue a run and start its process. Raises AlreadyRunning if one is active."""
    active = current()
    if active:
        raise AlreadyRunning(active)
    run = AnalysisRun(
        id=run_id or new_run_id(),
        trigger=trigger,
        include_placebo=include_placebo,
        refresh_data=refresh_data,
        status="queued",
        created_at=_now(),
        heartbeat_at=_now(),
    )
    save(run)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(run.id, encoding="utf-8")
    try:
        spawn(run)
    except Exception as exc:
        run.status, run.error, run.finished_at = "failed", f"could not start: {exc}", _now()
        save(run)
        LOCK_PATH.unlink(missing_ok=True)
    return run


class Reporter:
    """Used inside the run process to publish progress, logs and the outcome."""

    def __init__(self, run_id: str):
        run = load(run_id)
        if run is None:
            raise RuntimeError(f"no run record {run_id}")
        self.run = run
        self._lock = threading.Lock()
        self._stop = threading.Event()
        with self._lock:
            self.run.status = "running"
            self.run.started_at = _now()
            self.run.heartbeat_at = _now()
            save(self.run)
        self._beat = threading.Thread(target=self._heartbeat, daemon=True)
        self._beat.start()

    def _heartbeat(self) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            with self._lock:
                self.run.heartbeat_at = _now()
                save(self.run)

    def step(self, name: str, progress: float) -> None:
        with self._lock:
            self.run.step = name
            self.run.progress = max(self.run.progress, min(1.0, progress))
            self._append(f"{name}")
            save(self.run)

    def log(self, line: str) -> None:
        with self._lock:
            self._append(line)
            save(self.run)

    def _append(self, line: str) -> None:
        self.run.log.append(f"{_now():%H:%M:%S} {line}")
        self.run.log = self.run.log[-LOG_LINES_KEPT:]
        print(line, flush=True)

    def finish(self, ok: bool, summary: dict | None = None, changes: list[LabelChange] | None = None, error: str | None = None) -> None:
        self._stop.set()
        with self._lock:
            self.run.status = "succeeded" if ok else "failed"
            self.run.finished_at = _now()
            self.run.heartbeat_at = _now()
            self.run.progress = 1.0 if ok else self.run.progress
            self.run.step = "done" if ok else "failed"
            self.run.summary = summary or {}
            self.run.changes = changes or []
            self.run.error = error
            save(self.run)
        if LOCK_PATH.exists() and LOCK_PATH.read_text(encoding="utf-8").strip() == self.run.id:
            LOCK_PATH.unlink(missing_ok=True)
