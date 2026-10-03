"""The journal: every suggestion the strategy made, what you decided, and how it played out.

One record per suggestion, in data/journal/suggestions.json. This file can't be
regenerated from market data (your decisions and notes live here), so writes
are atomic, a dated copy is kept in data/journal/backups/ once a day, and
every read-modify-write (the runner's refresh, a decision from the API, the
data sync) happens inside `locked()` so none of them overwrites another.

Every suggestion is followed to its outcome automatically with the strategy's
own levels ("paper" outcome, used by the drift check and the feedback loop),
whether you took it or not. If you took or modified it, it is also followed
with the levels you acted on; that result is the journal's outcome_pnl.
"""

from __future__ import annotations

import json
import shutil
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

from orbit.config.settings import DATA_DIR
from orbit.core.types import Decision, JournalEntry, TradeSuggestion
from orbit.fsutil import atomic_write_text, file_lock

JOURNAL_DIR = DATA_DIR / "journal"
PATH = JOURNAL_DIR / "suggestions.json"
BACKUPS = JOURNAL_DIR / "backups"


class Outcome(BaseModel):
    entry_date: str
    entry: float
    exit_date: str
    exit_price: float
    reason: str  # target / stop / time
    return_pct: float  # net of costs
    r_multiple: float


class SuggestionRecord(BaseModel):
    id: str
    created_at: datetime
    signal_date: str  # the confirmation bar's time (ISO, UTC; a plain date in records from before timeframes)
    timeframe: str = "1d"  # the bars this suggestion lives on: 4h or 1d
    divergence_id: str | None = None  # the divergence it came from (strategy/divergence_model.py)
    risk_reward: float
    suggestion: TradeSuggestion
    features: dict[str, float]
    status: Literal["pending", "decided", "expired"] = "pending"
    decision: Decision | None = None
    decided_at: datetime | None = None
    notes: str = ""
    # Levels actually acted on (differ from the suggestion only for MODIFIED).
    acted_entry: float | None = None
    acted_stop: float | None = None
    acted_target: float | None = None
    paper: Outcome | None = None  # the strategy's own levels
    acted: Outcome | None = None  # your levels, if you took it
    # If someone else decided the same suggestion on another machine later (the data sync keeps the first
    # decision): theirs, with its levels and outcome, so no decision or trade is ever lost.
    other_decisions: list[dict] = []

    def journal_entry(self) -> JournalEntry:
        s = self.suggestion
        if self.decision == Decision.MODIFIED:
            s = s.model_copy(update={"entry_price": self.acted_entry, "stop_loss": self.acted_stop, "take_profit": self.acted_target})
        pnl = self.acted.return_pct if self.acted and self.decision in (Decision.TAKEN, Decision.MODIFIED) else None
        return JournalEntry(suggestion=s, decision=self.decision, notes=self.notes, outcome_pnl=pnl)


def load() -> list[SuggestionRecord]:
    if not PATH.exists():
        return []
    return [SuggestionRecord.model_validate(r) for r in json.loads(PATH.read_text(encoding="utf-8"))]


@contextmanager
def locked():
    """Hold the journal lock for a load -> change -> save sequence."""
    with file_lock(PATH.with_name("suggestions.lock")):
        yield


def save(records: list[SuggestionRecord]) -> None:
    atomic_write_text(PATH, json.dumps([r.model_dump(mode="json") for r in records], indent=1))
    BACKUPS.mkdir(parents=True, exist_ok=True)
    today = BACKUPS / f"suggestions-{datetime.now(timezone.utc):%Y-%m-%d}.json"
    if not today.exists():
        shutil.copyfile(PATH, today)


def get(records: list[SuggestionRecord], sid: str) -> SuggestionRecord | None:
    return next((r for r in records if r.id == sid), None)
