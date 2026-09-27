"""Moving event calendars in time, for placebo checks.

Exact moments themselves are computed by the Vedic event detector
(orbit/vedic/events.py), which pins every event to the second.
"""

from __future__ import annotations

from datetime import timedelta

from orbit.core.types import TransitEvent


def shift(events: list[TransitEvent], days: int) -> list[TransitEvent]:
    """Move events (and their exact times) by whole days, for placebo calendars."""
    delta = timedelta(days=days)
    return [
        e.model_copy(update={"date": e.date + delta, "exact_time": e.exact_time + delta if e.exact_time else None})
        for e in events
    ]
