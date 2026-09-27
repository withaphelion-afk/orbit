"""Event labels for display. Detection itself lives in orbit/vedic/events.py
(Vedic rules only; the earlier tropical detector was removed)."""

from __future__ import annotations

from orbit.core.types import TransitEvent


def event_label(e: TransitEvent) -> str:
    return e.label or f"{e.planet.value} {e.event_type.value} {e.to_state}".strip()
