from datetime import datetime, timedelta, timezone

import pytest

from orbit.analysis import jobs
from orbit.runner import schedule

AT = schedule.parse_hhmm("00:30")
UTC = timezone.utc


def at(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


# ---------------------------------------------------------------- schedule


def test_due_right_after_the_slot_and_not_before():
    before = schedule.analysis_decision(at(2026, 9, 28, 0, 29), AT, 6, at(2026, 9, 27, 0, 31), active=False)
    after = schedule.analysis_decision(at(2026, 9, 28, 0, 31), AT, 6, at(2026, 9, 27, 0, 31), active=False)
    assert not before.due
    assert after.due and after.slot == at(2026, 9, 28, 0, 30)


def test_catches_up_later_in_the_day_but_not_twice():
    # Machine was off at 00:30; runner comes up at 17:00 -> run now.
    assert schedule.analysis_decision(at(2026, 9, 28, 17, 0), AT, 6, at(2026, 9, 27, 0, 31), active=False).due
    # A manual run already succeeded after today's slot -> nothing to do.
    assert not schedule.analysis_decision(at(2026, 9, 28, 17, 0), AT, 6, at(2026, 9, 28, 9, 0), active=False).due


def test_never_overlaps_an_active_run():
    assert not schedule.analysis_decision(at(2026, 9, 28, 0, 31), AT, 6, None, active=True).due


def test_sunday_slot_includes_placebo():
    sunday = schedule.analysis_decision(at(2026, 9, 27, 1, 0), AT, 6, None, active=False)
    monday = schedule.analysis_decision(at(2026, 9, 28, 1, 0), AT, 6, None, active=False)
    assert sunday.include_placebo and not monday.include_placebo


def test_failed_run_is_retried_after_an_hour_at_most_three_times():
    now = at(2026, 9, 28, 2, 0)
    assert not schedule.analysis_decision(now, AT, 6, None, False, [now - timedelta(minutes=20)]).due
    assert schedule.analysis_decision(now, AT, 6, None, False, [now - timedelta(minutes=61)]).due
    assert not schedule.analysis_decision(now, AT, 6, None, False, [now - timedelta(hours=h) for h in (3, 2.5, 1.2)]).due


def test_wakes_for_the_sooner_event_but_at_least_every_five_minutes():
    now = at(2026, 9, 28, 0, 0)
    assert schedule.seconds_until_next_wake(now, now + timedelta(hours=1), now + timedelta(minutes=2)) == 120
    assert schedule.seconds_until_next_wake(now, now + timedelta(hours=1), now + timedelta(hours=3)) == 300


# ---------------------------------------------------------------- jobs


@pytest.fixture
def job_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "ANALYSIS_DIR", tmp_path)
    monkeypatch.setattr(jobs, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(jobs, "LOCK_PATH", tmp_path / "run.lock")
    return tmp_path


def test_only_one_run_at_a_time(job_dirs):
    started = []
    first = jobs.start("manual", spawn=started.append)
    assert started == [first] and jobs.current().id == first.id
    with pytest.raises(jobs.AlreadyRunning):
        jobs.start("schedule", spawn=started.append)


def test_abandoned_run_releases_the_lock(job_dirs):
    run = jobs.start("manual", spawn=lambda r: None)
    run.heartbeat_at = datetime.now(UTC) - timedelta(seconds=jobs.HEARTBEAT_STALE_SECONDS + 5)
    run.created_at = run.heartbeat_at
    jobs.save(run)
    assert jobs.current() is None
    assert jobs.load(run.id).status == "failed"
    jobs.start("manual", spawn=lambda r: None)  # the lock is free again


def test_reporter_publishes_progress_and_outcome(job_dirs):
    run = jobs.start("manual", spawn=lambda r: None)
    rep = jobs.Reporter(run.id)
    rep.step("Testing BTC", 0.4)
    rep.finish(True, summary={"total_tests": 10})
    saved = jobs.load(run.id)
    assert saved.status == "succeeded" and saved.progress == 1.0 and saved.summary == {"total_tests": 10}
    assert any("Testing BTC" in line for line in saved.log)
    assert jobs.current() is None and jobs.last_successful().id == run.id


def test_a_failed_spawn_is_recorded_not_left_running(job_dirs):
    def boom(_):
        raise OSError("no python")

    run = jobs.start("manual", spawn=boom)
    assert run.status == "failed" and "no python" in run.error
    assert jobs.current() is None
