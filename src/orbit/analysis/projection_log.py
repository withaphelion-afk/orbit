"""The forward track record: every projection as it was made, graded later
against what the price actually did.

Kept in data/analysis/projections_log.json, which is published with the other
analysis files (outputs.py), so it survives from one cloud job to the next.
The rules that keep it honest:

- A projection is recorded once, by id, with the time it was made. Its
  prediction is never changed afterwards: a later playbook may relabel the
  pattern, but the log keeps what was actually said at the time.
- It is graded only once its horizon has fully elapsed in stored, completed
  daily bars, with the playbook's own labelling (outcomes.label_outcomes) at
  the event's bar (outcomes.bar_index_for). The series is cut at the window's
  last bar first, so a grade uses nothing after what the label needs and comes
  out the same whenever it is computed.
- The summary sets each label's hit rate beside the average base rate of the
  same graded rows: what chance alone would have scored.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from orbit.config.settings import DATA_DIR
from orbit.core.types import Asset, ConfidenceLabel, LoggedProjection, Projection, ProjectionTrack, TrackBucket
from orbit.fsutil import atomic_write_text, file_lock
from orbit.analysis.confidence import RANK
from orbit.analysis.outcomes import CODE_TO_OUTCOME, UNDEFINED, bar_index_for, label_outcomes
from orbit.analysis.series import PriceSeries, day64, load_price_series

LOG_PATH = DATA_DIR / "analysis" / "projections_log.json"
RECENT = 20


def _utc(d: datetime) -> datetime:
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def load(path: Path | None = None) -> list[LoggedProjection]:
    path = path or LOG_PATH
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [LoggedProjection.model_validate(row) for row in data.get("entries", [])]


def _save(entries: list[LoggedProjection], path: Path) -> None:
    body = {"entries": [e.model_dump(mode="json") for e in entries]}
    atomic_write_text(path, json.dumps(body, separators=(",", ":")))


@contextmanager
def _locked(path: Path):
    with file_lock(path.with_suffix(".lock")):
        yield


def record(projections: list[Projection], now: datetime, path: Path | None = None) -> int:
    """Append projections not logged yet (by id). Returns how many were added.
    Ids already in the log are left exactly as they were first recorded."""
    path = path or LOG_PATH
    now = _utc(now)
    with _locked(path):
        entries = load(path)
        known = {e.projection.id for e in entries}
        added = 0
        for p in projections:
            if p.id in known:
                continue
            entries.append(LoggedProjection(projection=p.model_copy(deep=True), recorded_at=now))
            known.add(p.id)
            added += 1
        if added:
            _save(entries, path)
    return added


def _head(series: PriceSeries, k: int) -> PriceSeries:
    return PriceSeries(series.asset, series.dates[:k], series.open[:k], series.high[:k], series.low[:k], series.close[:k])


def grade(
    now: datetime,
    path: Path | None = None,
    series_for: Callable[[Asset], PriceSeries] | None = None,
) -> list[LoggedProjection]:
    """Grade every logged projection whose window has fully elapsed in stored daily
    bars. Returns the rows graded (or voided) by this call."""
    path = path or LOG_PATH
    now = _utc(now)
    today = day64(now)
    loader = series_for or (lambda a: load_price_series(a, until=now))
    series_cache: dict[Asset, PriceSeries] = {}
    labels_cache: dict[tuple[Asset, int, int], object] = {}
    done: list[LoggedProjection] = []
    with _locked(path):
        entries = load(path)
        for row in entries:
            if row.graded_at is not None:
                continue
            p = row.projection
            if p.asset not in series_cache:
                s = loader(p.asset)
                # Completed bars only, even if a loader hands over today's forming one.
                series_cache[p.asset] = _head(s, int(np.searchsorted(s.dates, today, side="left")))
            series = series_cache[p.asset]
            day = day64(p.event.date)
            if not len(series) or series.dates[-1] < day:
                continue  # the event's bar isn't stored yet
            i = bar_index_for(series.dates, day)
            if i is None:
                row.void_reason = "no stored price bar within 3 days of the event"
                row.graded_at = now
                done.append(row)
                continue
            last = i + p.horizon_days
            if last >= len(series):
                continue  # the horizon hasn't closed in stored bars yet
            key = (p.asset, last, p.horizon_days)
            if key not in labels_cache:
                labels_cache[key] = label_outcomes(_head(series, last + 1), p.horizon_days)
            o = labels_cache[key]
            row.graded_at = now
            row.graded_through = datetime.fromisoformat(str(series.dates[last])).replace(tzinfo=timezone.utc)
            code = int(o.codes[i])
            if code == UNDEFINED:
                row.void_reason = "the outcome could not be labelled (too little price history before the event)"
            else:
                row.actual_outcome = CODE_TO_OUTCOME[code]
                row.forward_return = float(o.forward_return[i])
                row.hit = row.actual_outcome == p.outcome
            done.append(row)
        if done:
            _save(entries, path)
    return done


def _bucket(rows: list[LoggedProjection]) -> TrackBucket:
    graded = [r for r in rows if r.hit is not None]
    void = sum(1 for r in rows if r.void_reason is not None)
    hits = sum(1 for r in graded if r.hit)
    return TrackBucket(
        recorded=len(rows),
        pending=len(rows) - len(graded) - void,
        graded=len(graded),
        void=void,
        hits=hits,
        hit_rate=hits / len(graded) if graded else None,
        avg_base_rate=float(np.mean([r.projection.base_rate for r in graded])) if graded else None,
    )


def summarize(entries: list[LoggedProjection]) -> ProjectionTrack:
    by_label: dict[str, list[LoggedProjection]] = {}
    for e in entries:
        by_label.setdefault(e.projection.label.value, []).append(e)
    order = sorted(by_label, key=lambda k: -RANK[ConfidenceLabel(k)])
    graded = [e for e in entries if e.hit is not None]
    recent = sorted(graded, key=lambda e: (e.graded_through, e.recorded_at), reverse=True)[:RECENT]
    if graded:
        note = ("Hit rate is the share of graded projections whose projected outcome happened; the average base rate is "
                "what chance alone would have scored on the same projections. Weak and none rows are unproven by definition.")
    else:
        note = "Nothing graded yet: a projection is graded only after its full horizon has passed in stored daily bars."
    return ProjectionTrack(
        first_recorded_at=min((e.recorded_at for e in entries), default=None),
        total=_bucket(entries),
        by_label={k: _bucket(by_label[k]) for k in order},
        recent=recent,
        note=note,
    )


def summary(path: Path | None = None) -> ProjectionTrack:
    return summarize(load(path))
