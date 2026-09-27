"""When the runner should refresh data and start the daily analysis run.

Pure functions of the clock and the last things that happened, so the
schedule can be tested without waiting for real time to pass.

- Data cycle: every RUNNER_INTERVAL_SECONDS.
- Analysis: once a day at ANALYSIS_DAILY_AT_UTC (00:30 by default, after the
  00:00 UTC daily close). If the machine was off or asleep then, it runs as
  soon as the runner is next up that day ("catch-up"), unless an analysis run
  (manual or scheduled) already succeeded since that day's slot. Sunday's run
  (PLACEBO_WEEKDAY) also runs the placebo check.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone


def parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm), tzinfo=timezone.utc)


def slot_on(day: datetime, at: time) -> datetime:
    return datetime(day.year, day.month, day.day, at.hour, at.minute, tzinfo=timezone.utc)


def latest_slot(now: datetime, at: time) -> datetime:
    """The most recent scheduled moment at or before `now`."""
    today = slot_on(now, at)
    return today if now >= today else today - timedelta(days=1)


def next_slot(now: datetime, at: time) -> datetime:
    today = slot_on(now, at)
    return today if now < today else today + timedelta(days=1)


@dataclass
class AnalysisDecision:
    due: bool
    slot: datetime  # the scheduled moment this decision is about
    include_placebo: bool
    next_at: datetime  # the next scheduled moment after `now`


MAX_ATTEMPTS_PER_SLOT = 3
RETRY_AFTER = timedelta(hours=1)


def analysis_decision(
    now: datetime,
    at: time,
    placebo_weekday: int,
    last_success_started: datetime | None,
    active: bool,
    failed_since_slot: list[datetime] = (),
) -> AnalysisDecision:
    """`failed_since_slot`: finish times of scheduled runs for this slot that failed.
    A failing run is retried after RETRY_AFTER, at most MAX_ATTEMPTS_PER_SLOT times."""
    slot = latest_slot(now, at)
    done = last_success_started is not None and last_success_started >= slot
    backing_off = bool(failed_since_slot) and now - max(failed_since_slot) < RETRY_AFTER
    exhausted = len(failed_since_slot) >= MAX_ATTEMPTS_PER_SLOT
    due = not active and not done and not backing_off and not exhausted
    return AnalysisDecision(due=due, slot=slot, include_placebo=slot.weekday() == placebo_weekday, next_at=next_slot(now, at))


def seconds_until_next_wake(now: datetime, next_data: datetime, next_analysis: datetime, cap_seconds: int = 300) -> float:
    """Sleep until the sooner of the two, but wake at least every `cap_seconds`
    so a changed clock, a finished manual run, or sleep/resume is noticed."""
    soonest = min(next_data, next_analysis)
    return max(1.0, min(cap_seconds, (soonest - now).total_seconds()))
