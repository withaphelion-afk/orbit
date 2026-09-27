"""The cross-platform launcher (scripts/start_orbit.py and friends). CI runs this on Windows, macOS and Linux."""

import sys
import time

import pytest

from orbit import launcher


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "RUN_DIR", tmp_path / "run")
    monkeypatch.setattr(launcher, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(launcher, "DATA", tmp_path)
    return tmp_path


def test_spawn_find_and_terminate_a_detached_process(dirs):
    sleeper = launcher.Service("sleeper", ["-c", "import time; time.sleep(120)"], "test sleeper")
    pid = launcher.spawn(sleeper)
    try:
        assert launcher.alive(pid)
        assert launcher.running_pid(sleeper) == pid
        assert (dirs / "run" / "sleeper.json").exists()
    finally:
        launcher.terminate(pid)
    deadline = time.time() + 10
    while time.time() < deadline and launcher.alive(pid):
        time.sleep(0.2)
    assert not launcher.alive(pid)
    assert launcher.running_pid(sleeper) is None


def test_a_dead_or_recycled_pid_is_not_running(dirs):
    (dirs / "run").mkdir()
    (dirs / "run" / "api.json").write_text('{"pid": 999999}', encoding="utf-8")
    assert launcher.running_pid(launcher.API) is None
    assert not launcher.alive(0) and not launcher.alive(-1)


def test_autostart_install_and_remove(tmp_path, monkeypatch):
    for var in ("HOME", "USERPROFILE", "APPDATA", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(var, str(tmp_path))
    path = launcher.autostart_path()
    assert str(path).startswith(str(tmp_path))
    launcher.install_autostart(say=lambda _: None)
    text = path.read_text(encoding="utf-8")
    assert "start_orbit.py" in text and "--no-browser" in text
    launcher.remove_autostart(say=lambda _: None)
    assert not path.exists()


def test_python_prefers_the_project_venv():
    py = launcher.python()
    assert py.endswith(("python.exe", "python")) or py == sys.executable
