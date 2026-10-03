import subprocess

from orbit import outputs


def _setup(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    monkeypatch.setattr(outputs, "_remote_url", lambda: str(remote))
    monkeypatch.setattr(outputs, "WORK", tmp_path / "work")
    monkeypatch.setattr(outputs, "STATE", tmp_path / "state.json")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_publish_then_fetch_roundtrip(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    src = tmp_path / "src"
    _write(src / "analysis" / "BTC.json", '{"a": 1}')
    _write(src / "analysis" / "run.lock", "x")  # never shared
    _write(src / "strategy" / "backtest" / "summary.json", "{}")
    _write(src / "runner_status.json", "{}")
    _write(src / "journal" / "suggestions.json", "[]")  # the journal goes through datasync, not here
    _write(src / "logs" / "runner.log", "".join(f"line {i}\n" for i in range(3000)))

    assert outputs.publish(src) == 4

    dst = tmp_path / "dst"
    assert outputs.fetch(dst) == 4
    assert (dst / "analysis" / "BTC.json").read_text(encoding="utf-8") == '{"a": 1}'
    assert not (dst / "analysis" / "run.lock").exists()
    assert not (dst / "journal").exists()
    assert len((dst / "logs" / "runner.log").read_text(encoding="utf-8").splitlines()) == outputs.LOG_LINES_KEPT

    # Nothing new published: nothing to take.
    assert outputs.fetch(dst) == 0


def test_republish_replaces_instead_of_growing_history(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    src = tmp_path / "src"
    for i in range(3):
        _write(src / "analysis" / "meta.json", f'{{"run": {i}}}')
        outputs.publish(src)
    remote = outputs._remote_url()
    count = subprocess.run(["git", "--git-dir", remote, "rev-list", "--count", outputs.BRANCH], capture_output=True, text=True, check=True)
    assert count.stdout.strip() == "1"
    dst = tmp_path / "dst"
    outputs.fetch(dst)
    assert (dst / "analysis" / "meta.json").read_text(encoding="utf-8") == '{"run": 2}'
