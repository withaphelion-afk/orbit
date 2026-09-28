"""The GitHub data sync (orbit/datasync.py): merge rules, and two machines syncing through a local stand-in for GitHub."""

import json
import subprocess
from pathlib import Path

import pytest

from orbit import datasync
from orbit.journal import store

REAL_GIT = datasync._git  # conftest.py blocks it for every other test
HEADER = "timestamp,open,high,low,close,volume,source\r\n"


def _csv(rows: list[tuple[str, str]]) -> bytes:
    """rows of (date, source) -> candle CSV bytes, exactly as storage.save_candles writes them (CRLF)."""
    body = "".join(f"{d}T00:00:00+00:00,1.0,2.0,0.5,1.5,10.0,{src}\r\n" for d, src in rows)
    return (HEADER + body).encode()


def _git(*args, cwd):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True)


# ---------------------------------------------------------------- merge rules


def test_csv_ranking_rules(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_bytes(_csv([("2026-01-01", "binance:BTCUSDT"), ("2026-01-02", "binance:BTCUSDT")]))
    b.write_bytes(_csv([("2026-01-01", "binance:BTCUSDT")]))
    assert datasync.csv_winner(a, b) == "local"  # later last bar
    b.write_bytes(a.read_bytes())
    assert datasync.csv_winner(a, b) == "remote"  # a tie keeps GitHub's copy
    spot = _csv([("2026-01-01", "dukascopy:XAGUSD")])
    futures = _csv([("2026-01-01", "yahoo:SI=F"), ("2026-01-05", "yahoo:SI=F")])
    a.write_bytes(futures)
    b.write_bytes(spot)
    assert datasync.csv_winner(a, b) == "remote"  # spot beats futures even with an older last bar
    a.write_bytes(HEADER.encode() + b"2026-01-09T00:00:00+00:00,1.0,2.0")  # cut off mid-write
    assert not datasync.csv_info(a).valid and datasync.csv_winner(a, b) == "remote"
    assert datasync.csv_winner(tmp_path / "missing.csv", tmp_path / "missing2.csv") is None


def test_journal_merge_rules():
    pending = {"id": "X", "created_at": "2026-01-01T00:00:00Z", "status": "pending", "decided_at": None, "paper": {"r_multiple": 1.0}}
    taken_late = {**pending, "status": "decided", "decision": "TAKEN", "decided_at": "2026-01-02T10:00:00Z", "paper": None}
    skipped_early = {**pending, "status": "decided", "decision": "SKIPPED", "decided_at": "2026-01-02T09:00:00Z", "paper": None}
    other = {"id": "Y", "created_at": "2026-01-03T00:00:00Z", "status": "expired"}
    merged = datasync.merge_journal([pending, other], [taken_late])
    assert [r["id"] for r in merged] == ["X", "Y"]
    assert merged[0]["decision"] == "TAKEN" and merged[0]["paper"] == {"r_multiple": 1.0}  # decision wins, outcome kept
    assert datasync.merge_journal([taken_late], [skipped_early])[0]["decision"] == "SKIPPED"  # first decision stands
    assert datasync.merge_journal([], [other]) == [other]


# ---------------------------------------------------------------- two machines


class Machines:
    """Two clones of one bare repo standing in for GitHub; `use(name)` points datasync at one of them."""

    def __init__(self, root: Path, monkeypatch):
        self.root, self.mp = root, monkeypatch
        self.remote = root / "github.git"
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True)
        for name in ("a", "b"):
            repo = root / name
            repo.mkdir()
            _git("init", "-q", "-b", "main", cwd=repo)
            _git("remote", "add", "origin", str(self.remote), cwd=repo)
            (repo / "README.md").write_text(name)
            _git("add", ".", cwd=repo)
            _git("commit", "-q", "-m", "init", cwd=repo)
        monkeypatch.setattr(datasync, "DATA_SYNC_ENABLED", True)
        monkeypatch.setattr(datasync, "_git", REAL_GIT)
        monkeypatch.setattr(datasync, "DATA_SYNC_REMOTE", "origin")
        monkeypatch.setattr(datasync, "DATA_SYNC_BRANCH", "data")

    def data(self, name: str) -> Path:
        return self.root / name / "data"

    def use(self, name: str) -> None:
        repo = self.root / name
        for attr, value in (("REPO_ROOT", repo), ("DATA_DIR", repo / "data"), ("WORKTREE", repo / ".orbit-sync"),
                            ("STATE", repo / "data/run/sync.json"), ("LOCK", repo / "data/run/sync.lock")):
            self.mp.setattr(datasync, attr, value)
        self.mp.setattr(store, "PATH", repo / "data/journal/suggestions.json")

    def sync(self, name: str, **kw) -> datasync.Result:
        self.use(name)
        return datasync.sync(**kw)

    def on_github(self, path: str) -> bytes:
        return subprocess.run(["git", "--git-dir", str(self.remote), "show", f"data:{path}"], check=True, capture_output=True).stdout


@pytest.fixture
def machines(tmp_path, monkeypatch):
    return Machines(tmp_path, monkeypatch)


def _put(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_a_fresh_machine_gets_everything_byte_for_byte(machines):
    a = machines.data("a")
    btc = _csv([("2026-01-01", "binance:BTCUSDT"), ("2026-01-02", "binance:BTCUSDT")])
    _put(a / "BTC_1d.csv", btc)
    _put(a / "history_report.json", json.dumps({"BTC": {"bars": 2}}, indent=2).encode())
    _put(a / "cache/dukascopy/XAGUSD/2003/2003-05.hour.bi5", b"\x00\x01binary\r\n")
    _put(a / "cache/dukascopy/XAGUSD/2003/2003-06.hour.empty", b"")
    _put(a / "cache/dukascopy/XAGUSD/2003/2003-07.hour.part", b"half a download")
    _put(a / "ephemeris_cache/de421.bsp", b"kernel")
    _put(a / "analysis/placebo.json", b'{"checked_at": "2026-01-01T00:00:00Z"}')
    _put(a / "journal/suggestions.json", b'[{"id": "X", "status": "pending"}]')
    _put(a / "features/BTC.csv", b"rebuilt locally, never shared")

    first = machines.sync("a")
    assert first.commit and "BTC_1d.csv" in first.pushed
    assert machines.on_github("BTC_1d.csv") == btc  # CRLF intact

    got = machines.sync("b", push=False)
    b = machines.data("b")
    for rel in ("BTC_1d.csv", "history_report.json", "cache/dukascopy/XAGUSD/2003/2003-05.hour.bi5",
                "cache/dukascopy/XAGUSD/2003/2003-06.hour.empty", "ephemeris_cache/de421.bsp", "analysis/placebo.json"):
        assert (b / rel).read_bytes() == (a / rel).read_bytes(), rel
        assert rel in got.pulled
    assert not (b / "cache/dukascopy/XAGUSD/2003/2003-07.hour.part").exists()
    assert not (b / "journal/suggestions.json").exists()  # the journal stays local unless turned on
    assert not (b / "features/BTC.csv").exists()
    assert machines.sync("a").pushed == []  # nothing new: no empty commits


def test_each_machine_adds_and_both_converge(machines):
    a, b = machines.data("a"), machines.data("b")
    _put(a / "BTC_1d.csv", _csv([("2026-01-01", "binance:BTCUSDT")]))
    machines.sync("a")
    machines.sync("b")
    _put(b / "BTC_1d.csv", _csv([("2026-01-01", "binance:BTCUSDT"), ("2026-01-02", "binance:BTCUSDT")]))  # B fetched a newer bar
    _put(a / "cache/dukascopy/XAGUSD/2004/2004-01.hour.bi5", b"jan")  # A downloaded more silver
    _put(b / "SILVER_1d.csv", _csv([("2003-05-05", "dukascopy:XAGUSD")]))  # B finished the spot rebuild
    _put(a / "SILVER_1d.csv", _csv([("2000-08-30", "yahoo:SI=F"), ("2026-01-02", "yahoo:SI=F")]))  # A still on futures
    machines.sync("a")
    machines.sync("b")
    machines.sync("a")
    for rel in ("BTC_1d.csv", "SILVER_1d.csv", "cache/dukascopy/XAGUSD/2004/2004-01.hour.bi5"):
        assert (a / rel).read_bytes() == (b / rel).read_bytes() == machines.on_github(rel), rel
    assert b"2026-01-02" in (a / "BTC_1d.csv").read_bytes()
    assert b"dukascopy" in (a / "SILVER_1d.csv").read_bytes()


def test_journals_merge_when_shared(machines):
    a, b = machines.data("a"), machines.data("b")
    _put(a / "journal/suggestions.json", json.dumps([{"id": "X", "created_at": "2026-01-01", "status": "pending"}]).encode())
    machines.sync("a", include_journal=True)
    decided = {"id": "X", "created_at": "2026-01-01", "status": "decided", "decision": "TAKEN", "decided_at": "2026-01-02T00:00:00Z"}
    _put(b / "journal/suggestions.json", json.dumps([decided, {"id": "Y", "created_at": "2026-01-03", "status": "pending"}]).encode())
    machines.sync("b", include_journal=True)
    machines.sync("a", include_journal=True)
    merged = json.loads((a / "journal/suggestions.json").read_text())
    assert [(r["id"], r["status"]) for r in merged] == [("X", "decided"), ("Y", "pending")]
    assert json.loads((b / "journal/suggestions.json").read_text()) == merged


def test_a_rejected_push_fetches_and_merges_again(machines, monkeypatch):
    a, b = machines.data("a"), machines.data("b")
    _put(a / "ETH_1d.csv", _csv([("2026-01-01", "binance:ETHUSDT")]))
    machines.sync("a")
    machines.sync("b")  # B now has a (soon stale) copy of the branch
    _put(a / "cache/dukascopy/XAGUSD/2005/2005-01.hour.bi5", b"from a")
    machines.sync("a")  # A pushes while B isn't looking
    _put(b / "cache/dukascopy/XAGUSD/2005/2005-02.hour.bi5", b"from b")

    real_fetch, calls = datasync._fetch, []

    def stale_first(*args):
        calls.append(1)
        return True if len(calls) == 1 else real_fetch(*args)  # first round works from B's stale copy

    monkeypatch.setattr(datasync, "_fetch", stale_first)
    result = machines.sync("b")
    assert len(calls) >= 2  # rejected once, then fetched and merged again
    assert result.commit
    assert machines.on_github("cache/dukascopy/XAGUSD/2005/2005-01.hour.bi5") == b"from a"
    assert machines.on_github("cache/dukascopy/XAGUSD/2005/2005-02.hour.bi5") == b"from b"
    assert (b / "cache/dukascopy/XAGUSD/2005/2005-01.hour.bi5").read_bytes() == b"from a"


def test_skips_cleanly_outside_a_git_checkout(tmp_path, monkeypatch):
    monkeypatch.setattr(datasync, "DATA_SYNC_ENABLED", True)
    monkeypatch.setattr(datasync, "_git", REAL_GIT)
    monkeypatch.setattr(datasync, "REPO_ROOT", tmp_path)
    assert "git checkout" in datasync.sync().skipped
    monkeypatch.setattr(datasync, "DATA_SYNC_ENABLED", False)
    assert "turned off" in datasync.sync().skipped


# ---------------------------------------------------------------- what the review found


def test_the_test_suite_can_never_reach_the_real_sync():
    """conftest.py: with no stand-in set up, the sync is off and datasync's git is refused."""
    assert "turned off" in datasync.sync().skipped
    with pytest.raises(AssertionError):
        datasync._git("status")


def test_longer_history_beats_a_later_last_bar_and_prefer_local_wins_ties(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_bytes(_csv([("2013-01-01", "bitstamp:btcusd"), ("2026-01-01", "binance:BTCUSDT")]))
    b.write_bytes(_csv([("2017-08-17", "binance:BTCUSDT"), ("2026-01-02", "binance:BTCUSDT")]))
    assert datasync.csv_winner(a, b) == "local"  # the full history isn't replaced by a shorter one
    b.write_bytes(a.read_bytes().replace(b"1.5,10.0", b"1.6,10.0"))  # same bars, corrected values: a deliberate rebuild
    assert datasync.csv_winner(b, a) == "remote"
    assert datasync.csv_winner(b, a, prefer_local=True) == "local"


def test_conflicting_decisions_keep_both():
    saksham = {"id": "X", "status": "decided", "decision": "SKIPPED", "decided_at": "2026-09-20T09:00:00Z", "notes": "not for me"}
    raunak = {"id": "X", "status": "decided", "decision": "TAKEN", "decided_at": "2026-09-20T10:00:00Z", "notes": "bought 0.2 BTC",
              "acted": {"r_multiple": 2.0}}
    merged = datasync.merge_journal([raunak], [saksham])[0]
    assert merged["decision"] == "SKIPPED"  # the first decision stands
    assert "TAKEN" in merged["notes"] and "bought 0.2 BTC" in merged["notes"]  # the other one isn't lost
    assert datasync.merge_journal([merged], [saksham]) == [merged]  # merging again adds nothing


def test_a_sync_that_changes_the_journal_backs_it_up_first(machines):
    a, b = machines.data("a"), machines.data("b")
    mine = b'[{"id": "X", "created_at": "2026-01-01", "status": "decided", "decision": "TAKEN", "decided_at": "2026-01-02T10:00:00Z"}]'
    _put(a / "journal/suggestions.json", mine)
    theirs = b'[{"id": "X", "created_at": "2026-01-01", "status": "decided", "decision": "SKIPPED", "decided_at": "2026-01-02T09:00:00Z"}]'
    _put(b / "journal/suggestions.json", theirs)
    machines.sync("b", include_journal=True)
    machines.sync("a", include_journal=True)
    backups = list((a / "journal" / "backups").glob("before-sync-*.json"))
    assert len(backups) == 1 and backups[0].read_bytes() == mine


def test_a_deleted_branch_is_not_resurrected(machines):
    a = machines.data("a")
    _put(a / "BTC_1d.csv", _csv([("2026-01-01", "binance:BTCUSDT")]))
    _put(a / "journal/suggestions.json", b'[{"id": "X", "status": "pending", "notes": "PRIVATE NOTE"}]')
    machines.sync("a", include_journal=True)
    subprocess.run(["git", "--git-dir", str(machines.remote), "branch", "-D", "data"], check=True, capture_output=True)
    _put(a / "BTC_1d.csv", _csv([("2026-01-01", "binance:BTCUSDT"), ("2026-01-02", "binance:BTCUSDT")]))
    with pytest.raises(datasync.SyncError, match="gone from GitHub"):
        machines.sync("a")
    heads = subprocess.run(["git", "--git-dir", str(machines.remote), "branch", "--list", "data"], capture_output=True, text=True).stdout
    assert not heads.strip()  # still gone
    machines.sync("a", recreate=True)  # asked for explicitly: a new, empty history with today's data only
    log = subprocess.run(["git", "--git-dir", str(machines.remote), "log", "--oneline", "data"], capture_output=True, text=True).stdout
    assert len(log.strip().splitlines()) == 2
    with pytest.raises(subprocess.CalledProcessError):
        machines.on_github("journal/suggestions.json")


def test_a_machine_that_cannot_push_still_pulls_and_backs_off(machines):
    a, b = machines.data("a"), machines.data("b")
    _put(a / "BTC_1d.csv", _csv([("2026-01-01", "binance:BTCUSDT")]))
    machines.sync("a")
    hook = machines.remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho no write access >&2\nexit 1\n", newline="\n")
    hook.chmod(0o755)
    _put(b / "ETH_1d.csv", _csv([("2026-01-01", "binance:ETHUSDT")]))
    result = machines.sync("b")
    assert "BTC_1d.csv" in result.pulled and (b / "BTC_1d.csv").exists()
    assert result.warning and "Couldn't send" in result.warning and not result.pushed
    assert not datasync.due()  # tries again tomorrow, not every hour
    head = REAL_GIT("rev-parse", "HEAD", cwd=datasync.WORKTREE).stdout
    assert head == REAL_GIT("rev-parse", datasync._remote_ref(), cwd=datasync.WORKTREE).stdout  # no unpushed commit left


def test_stray_temp_files_are_never_committed(machines):
    a = machines.data("a")
    _put(a / "BTC_1d.csv", _csv([("2026-01-01", "binance:BTCUSDT")]))
    machines.sync("a")
    (datasync.WORKTREE / ".BTC_1h.csv.4242.1.tmp").write_bytes(b"half a file")
    _put(a / "BTC_1d.csv", _csv([("2026-01-01", "binance:BTCUSDT"), ("2026-01-02", "binance:BTCUSDT")]))
    machines.sync("a")
    names = subprocess.run(["git", "--git-dir", str(machines.remote), "ls-tree", "--name-only", "data"], capture_output=True, text=True).stdout
    assert ".tmp" not in names


def test_journal_sharing_follows_the_setting_at_call_time(machines, monkeypatch):
    from orbit.config import settings

    a = machines.data("a")
    _put(a / "journal/suggestions.json", b'[{"id": "X", "status": "pending"}]')
    monkeypatch.setattr(settings, "DATA_SYNC_JOURNAL", True)
    machines.sync("a")
    assert b'"X"' in machines.on_github("journal/suggestions.json")


def test_due_backs_off_after_success_and_retries_sooner_after_an_error(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    monkeypatch.setattr(datasync, "STATE", tmp_path / "sync.json")
    now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    assert datasync.due(now)
    datasync._save_state(last_attempt=(now - timedelta(hours=5)).isoformat(), last_attempt_ok=True)
    assert not datasync.due(now)
    datasync._save_state(last_attempt_ok=False)
    assert datasync.due(now)


# ---------------------------------------------------------------- what the second check found


def _report(built_at: str) -> bytes:
    return json.dumps({"BTC": {"built_at": built_at}}, indent=2).encode()


def test_a_deliberate_rebuild_spreads_and_newer_bars_are_kept(machines):
    """A newer full build (history_report built_at) wins even with fewer rows, and the other machine's newer bar is added."""
    a, b = machines.data("a"), machines.data("b")
    old = [("2026-01-01", "binance:BTCUSDT"), ("2026-01-02", "binance:BTCUSDT"), ("2026-01-03", "binance:BTCUSDT")]
    _put(a / "BTC_1d.csv", _csv(old))
    _put(a / "history_report.json", _report("2026-01-01T00:00:00+00:00"))
    machines.sync("a")
    machines.sync("b")
    rebuilt = _csv([old[0], old[2]]).replace(b"1.5,10.0", b"1.7,10.0")  # a stub day dropped, closes corrected
    _put(a / "BTC_1d.csv", rebuilt)
    _put(a / "history_report.json", _report("2026-01-05T00:00:00+00:00"))
    _put(b / "BTC_1d.csv", _csv(old + [("2026-01-04", "binance:BTCUSDT")]))  # B meanwhile fetched a newer bar
    machines.sync("a")
    machines.sync("b")
    machines.sync("a")
    final = machines.on_github("BTC_1d.csv")
    assert final.startswith(rebuilt) and final.endswith(b"2026-01-04T00:00:00+00:00,1.0,2.0,0.5,1.5,10.0,binance:BTCUSDT\r\n")
    assert (a / "BTC_1d.csv").read_bytes() == (b / "BTC_1d.csv").read_bytes() == final
    assert json.loads((b / "history_report.json").read_text())["BTC"]["built_at"].startswith("2026-01-05")


def test_prefer_local_forces_this_machines_file(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_bytes(_csv([("2026-01-02", "binance:BTCUSDT")]))  # later start: would normally lose
    b.write_bytes(_csv([("2026-01-01", "binance:BTCUSDT"), ("2026-01-02", "binance:BTCUSDT")]))
    assert datasync.csv_winner(a, b) == "remote"
    assert datasync.csv_winner(a, b, prefer_local=True) == "local"


def test_the_other_decision_keeps_its_outcome():
    saksham = {"id": "X", "status": "decided", "decision": "SKIPPED", "decided_at": "2026-09-20T09:00:00Z", "notes": "not for me"}
    raunak = {"id": "X", "status": "decided", "decision": "TAKEN", "decided_at": "2026-09-20T10:00:00Z", "notes": "bought 0.2 BTC",
              "acted_entry": 100.0, "acted": {"r_multiple": 2.0}}
    merged = datasync.merge_journal([raunak], [saksham])[0]
    other = merged["other_decisions"][0]
    assert other["decision"] == "TAKEN" and other["acted"] == {"r_multiple": 2.0} and other["acted_entry"] == 100.0
    assert datasync.merge_journal([merged], [saksham]) == [merged] == datasync.merge_journal([saksham], [merged])


def test_other_decisions_survive_the_journal_model():
    from orbit.journal.store import SuggestionRecord

    assert "other_decisions" in SuggestionRecord.model_fields


def test_an_unreadable_local_journal_is_left_alone(machines):
    a, b = machines.data("a"), machines.data("b")
    _put(a / "journal/suggestions.json", b'[{"id": "Y", "created_at": "2026-01-01", "status": "pending"}]')
    machines.sync("a", include_journal=True)
    broken = b'[{"id": "X", "notes": "my notes"},]'
    _put(b / "journal/suggestions.json", broken)
    result = machines.sync("b", include_journal=True)
    assert "can't be read" in result.warning
    assert (b / "journal/suggestions.json").read_bytes() == broken


def test_a_stale_index_lock_in_the_worktree_is_cleared(machines):
    import os
    import time

    a = machines.data("a")
    _put(a / "BTC_1d.csv", _csv([("2026-01-01", "binance:BTCUSDT")]))
    machines.sync("a")
    lock = Path(REAL_GIT("rev-parse", "--git-path", "index.lock", cwd=datasync.WORKTREE).stdout.strip())
    lock = lock if lock.is_absolute() else datasync.WORKTREE / lock
    lock.write_text("")
    old = time.time() - 3600
    os.utime(lock, (old, old))
    _put(a / "BTC_1d.csv", _csv([("2026-01-01", "binance:BTCUSDT"), ("2026-01-02", "binance:BTCUSDT")]))
    assert machines.sync("a").commit  # the leftover lock didn't break it
    assert not lock.exists()


def test_recreate_over_an_existing_branch_replaces_it_in_one_step(machines):
    a = machines.data("a")
    for day in ("2026-01-01", "2026-01-02", "2026-01-03"):
        _put(a / "BTC_1d.csv", _csv([("2026-01-01", "binance:BTCUSDT"), (day, "binance:BTCUSDT")]))
        machines.sync("a")
    machines.sync("a", recreate=True)
    log = subprocess.run(["git", "--git-dir", str(machines.remote), "log", "--oneline", "data"], capture_output=True, text=True).stdout
    assert len(log.strip().splitlines()) == 2  # a fresh history: the start, and today's data


def test_a_push_failure_reports_the_real_reason(machines):
    a, b = machines.data("a"), machines.data("b")
    _put(a / "BTC_1d.csv", _csv([("2026-01-01", "binance:BTCUSDT")]))
    machines.sync("a")
    hook = machines.remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'GH001: large files detected' >&2\nexit 1\n", newline="\n")
    hook.chmod(0o755)
    _put(b / "ETH_1d.csv", _csv([("2026-01-01", "binance:ETHUSDT")]))
    result = machines.sync("b")
    assert "GH001" in result.warning or "declined" in result.warning
    assert "failed to push some refs" not in result.warning


def test_the_users_own_ssh_command_is_respected(monkeypatch):
    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
    env = datasync._env()
    assert "GIT_SSH_COMMAND" not in env and env["SSH_ASKPASS_REQUIRE"] == "never" and env["GIT_TERMINAL_PROMPT"] == "0"


def test_loose_objects_get_packed(machines):
    machines.use("a")
    repo = datasync.REPO_ROOT
    for k in range(60):  # reachable loose objects, like the blobs a sync commits
        (repo / "many" / f"{k}.txt").parent.mkdir(exist_ok=True)
        (repo / "many" / f"{k}.txt").write_text(f"file {k}")
    _git("add", "many", cwd=repo)
    _git("commit", "-q", "-m", "many files", cwd=repo)
    datasync._pack_loose_objects()
    counts = REAL_GIT("count-objects", "-v").stdout
    assert "count: 0" in counts
