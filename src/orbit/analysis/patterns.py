"""The hypothesis list: which Vedic patterns get tested.

Patterns come from orbit/vedic/patterns.py (the Jyotish definitions); this
module groups events into them. The full list is written out
(data/analysis/hypotheses.json) before any test runs, so the set of trials is
on record. All pattern tests for an asset are corrected together as one family.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from orbit.core.types import Planet, SpeedClass, TransitEvent, TransitEventType
from orbit.vedic import patterns as vedic
from orbit.vedic.zodiac import RASHIS


@dataclass
class Pattern:
    pattern_id: str
    description: str
    planet: Planet
    event_type: TransitEventType
    sign: str | None
    speed_class: SpeedClass
    events: list[TransitEvent] = field(default_factory=list)

    @property
    def family_key(self) -> str:
        # One family per asset for every pattern test. Splitting families lets each
        # claim its own false-discovery budget; a placebo check showed that roughly
        # doubled false alarms per asset.
        return "PATTERNS"


def build_patterns(events: list[TransitEvent], include_moon: bool = True) -> list[Pattern]:
    patterns: dict[str, Pattern] = {}
    for e in events:
        speed = vedic.speed_class(e)
        if speed == SpeedClass.LUNAR and not include_moon:
            continue
        for pid, desc in vedic.keys(e):
            p = patterns.get(pid)
            if p is None:
                sign = e.to_state if e.event_type == TransitEventType.INGRESS and pid.count(":") == 2 and e.to_state in RASHIS else None
                p = patterns[pid] = Pattern(pid, desc, e.planet, e.event_type, sign, speed)
            p.events.append(e)
    return sorted(patterns.values(), key=lambda p: p.pattern_id)


def patterns_for_event(e: TransitEvent) -> list[str]:
    """Pattern ids an event belongs to (empty for backward ingresses and re-entries)."""
    return [pid for pid, _ in vedic.keys(e)]
