from datetime import timedelta

import pytest

from orbit import cloud
from orbit.analysis import jobs


@pytest.fixture
def runs(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "ANALYSIS_DIR", tmp_path)
    monkeypatch.setattr(jobs, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(jobs, "LOCK_PATH", tmp_path / "run.lock")
    monkeypatch.setattr(cloud, "DISPATCHED", tmp_path / "dispatched.json")
    monkeypatch.setenv("ORBIT_DISPATCH_TOKEN", "test-token")
    return tmp_path


class _Response:
    def __init__(self, status_code, text=""):
        self.status_code, self.text = status_code, text


def _dispatch_ok(monkeypatch):
    sent = []
    monkeypatch.setattr(cloud.requests, "post", lambda url, **kw: sent.append((url, kw)) or _Response(204))
    return sent


def test_run_button_hands_the_run_to_github(runs, monkeypatch):
    sent = _dispatch_ok(monkeypatch)
    run = jobs.start("manual", include_placebo=True, refresh_data=False, spawn=cloud.dispatch)
    url, kw = sent[0]
    assert url.endswith("/actions/workflows/analysis.yml/dispatches")
    assert kw["json"]["inputs"] == {"placebo": "true", "refresh": "false", "run_id": run.id}
    assert jobs.load(run.id).step == "Waiting for GitHub Actions"
    assert jobs.current().id == run.id  # the terminal shows it as the active run


def test_github_refusing_marks_the_run_failed(runs, monkeypatch):
    monkeypatch.setattr(cloud.requests, "post", lambda url, **kw: _Response(403, "Resource not accessible"))
    run = jobs.start("manual", spawn=cloud.dispatch)
    assert run.status == "failed" and "403" in run.error
    assert jobs.current() is None


def test_tracking_follows_github_then_takes_the_published_record(runs, monkeypatch):
    _dispatch_ok(monkeypatch)
    run = jobs.start("manual", spawn=cloud.dispatch)

    cloud.track_dispatched(find=lambda rid: {"status": "in_progress", "html_url": "https://gh/run/1"})
    rec = jobs.load(run.id)
    assert rec.status == "running" and "GitHub run: https://gh/run/1" in rec.log

    def publish_real_record(force):
        real = jobs.load(run.id)
        real.status, real.log = "succeeded", ["the workflow's own log"]
        jobs.save(real)

    cloud.track_dispatched(find=lambda rid: {"status": "completed", "conclusion": "success"}, fetch_results=publish_real_record)
    rec = jobs.load(run.id)
    assert rec.status == "succeeded" and rec.log == ["the workflow's own log"]
    assert not cloud.DISPATCHED.exists() and jobs.current() is None


def test_workflow_that_failed_before_publishing(runs, monkeypatch):
    _dispatch_ok(monkeypatch)
    run = jobs.start("manual", spawn=cloud.dispatch)
    cloud.track_dispatched(find=lambda rid: {"status": "completed", "conclusion": "failure", "html_url": "u"},
                           fetch_results=lambda force: 0)
    rec = jobs.load(run.id)
    assert rec.status == "failed" and "failure" in rec.error


def test_run_github_never_listed_is_given_up(runs, monkeypatch):
    _dispatch_ok(monkeypatch)
    run = jobs.start("manual", spawn=cloud.dispatch)
    cloud.track_dispatched(find=lambda rid: None)
    assert jobs.load(run.id).status == "queued"  # still waiting, heartbeat refreshed
    monkeypatch.setattr(cloud, "UNSEEN_RUN_GIVE_UP", timedelta(seconds=-1))
    cloud.track_dispatched(find=lambda rid: None)
    assert jobs.load(run.id).status == "failed"
