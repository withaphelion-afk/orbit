from types import SimpleNamespace

from orbit.core.types import Decision
from orbit.journal import cli
from orbit.strategy import live


def test_logs_a_decision(monkeypatch):
    seen = {}

    def decide(sid, decision, notes, entry, stop, target):
        seen.update(sid=sid, decision=decision, notes=notes)
        return SimpleNamespace(id=sid, decision=decision)

    monkeypatch.setattr(live, "decide", decide)
    assert cli.main(["--id", "s1", "--decision", "TAKEN", "--notes", "looks clean"]) == 0
    assert seen == {"sid": "s1", "decision": Decision.TAKEN, "notes": "looks clean"}


def test_a_second_click_or_expired_suggestion_is_not_an_error(monkeypatch):
    def decide(*args):
        raise ValueError("suggestion s1 is already decided")

    monkeypatch.setattr(live, "decide", decide)
    assert cli.main(["--id", "s1", "--decision", "SKIPPED"]) == 0


def test_unknown_suggestion_and_incomplete_modify_fail(monkeypatch):
    def decide(*args):
        raise KeyError("nope")

    monkeypatch.setattr(live, "decide", decide)
    assert cli.main(["--id", "nope", "--decision", "SKIPPED"]) == 1
    assert cli.main(["--id", "s1", "--decision", "MODIFIED", "--entry", "1"]) == 2
