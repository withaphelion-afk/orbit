import logging

import pytest

from orbit.runner import loop


class _StopLoop(Exception):
    """Raised from a patched time.sleep to escape run_forever's infinite loop after N cycles."""


def test_run_forever_survives_a_failing_cycle(monkeypatch, caplog, tmp_path):
    call_count = {"n": 0}

    def fake_run_once(logger):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated network failure")
        # second call succeeds

    def fake_sleep(seconds):
        if call_count["n"] >= 2:
            raise _StopLoop

    monkeypatch.setattr(loop.status, "STATUS_PATH", tmp_path / "runner_status.json")
    monkeypatch.setattr(loop, "run_once", fake_run_once)
    monkeypatch.setattr(loop.time, "sleep", fake_sleep)

    with caplog.at_level(logging.ERROR, logger="orbit.runner"):
        with pytest.raises(_StopLoop):
            loop.run_forever(interval_seconds=0, schedule_analysis=False)

    # The failure was logged, and the loop reached a second cycle instead of dying.
    assert call_count["n"] == 2
    assert any("Cycle failed" in record.message for record in caplog.records)

    # The heartbeat recorded both cycles, the last one successful.
    beat = loop.status.read_status()
    assert beat["cycles"] == 2 and beat["last_cycle_ok"] is True
