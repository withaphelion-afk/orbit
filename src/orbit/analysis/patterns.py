"""The hypothesis list: exactly which transit patterns get tested.

Written out (data/analysis/hypotheses.json) before any test runs, so the full
set of trials is on record and nothing can be quietly added after looking at
results. Each pattern groups events two ways, because per-sign splits of
anything slower than Venus almost never reach the minimum sample:

    {PLANET}:INGRESS             every first-entry forward ingress
    {PLANET}:INGRESS:{Sign}      first-entry forward ingress into one sign
    {PLANET}:STATION_RETROGRADE  planet turns retrograde
    {PLANET}:STATION_DIRECT      planet turns direct

Backward ingresses and re-entries are recorded as events but not tested, so
one pass through a sign is counted once. All pattern tests for an asset are
corrected together as one family.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from orbit.core.types import Planet, SpeedClass, TransitEvent, TransitEventType
from orbit.data.ephemeris import ZODIAC_SIGNS
from orbit.analysis.transit_events import SPEED_CLASS, STATION_PLANETS


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
        # One family per asset for every pattern test (Moon included). Splitting
        # families lets each claim its own false-discovery budget; a placebo check
        # showed that roughly doubled false alarms per asset.
        return "PATTERNS"


def _title(p: Planet) -> str:
    return p.value.capitalize()


def build_patterns(events: list[TransitEvent], include_moon: bool) -> list[Pattern]:
    patterns: dict[str, Pattern] = {}

    def add(pid: str, desc: str, planet: Planet, etype: TransitEventType, sign: str | None) -> Pattern:
        if pid not in patterns:
            patterns[pid] = Pattern(pid, desc, planet, etype, sign, SPEED_CLASS[planet])
        return patterns[pid]

    # Declare every pattern up front, including ones that end up with no events,
    # so the hypothesis list doesn't depend on what the data happened to contain.
    for planet in Planet:
        if planet == Planet.MOON and not include_moon:
            continue
        add(f"{planet.value}:INGRESS", f"{_title(planet)} enters any sign", planet, TransitEventType.INGRESS, None)
        for sign in ZODIAC_SIGNS:
            add(f"{planet.value}:INGRESS:{sign}", f"{_title(planet)} enters {sign}", planet, TransitEventType.INGRESS, sign)
        if planet in STATION_PLANETS:
            add(f"{planet.value}:STATION_RETROGRADE", f"{_title(planet)} stations retrograde", planet, TransitEventType.STATION_RETROGRADE, None)
            add(f"{planet.value}:STATION_DIRECT", f"{_title(planet)} stations direct", planet, TransitEventType.STATION_DIRECT, None)

    for e in events:
        if e.planet == Planet.MOON and not include_moon:
            continue
        if e.event_type == TransitEventType.INGRESS:
            if e.backward or e.reentry:
                continue
            patterns[f"{e.planet.value}:INGRESS"].events.append(e)
            patterns[f"{e.planet.value}:INGRESS:{e.to_state}"].events.append(e)
        else:
            patterns[f"{e.planet.value}:{e.event_type.value}"].events.append(e)
    return list(patterns.values())


def patterns_for_event(e: TransitEvent) -> list[str]:
    """Pattern ids an event belongs to (empty for backward ingresses and re-entries)."""
    if e.event_type == TransitEventType.INGRESS:
        if e.backward or e.reentry:
            return []
        return [f"{e.planet.value}:INGRESS:{e.to_state}", f"{e.planet.value}:INGRESS"]
    return [f"{e.planet.value}:{e.event_type.value}"]
