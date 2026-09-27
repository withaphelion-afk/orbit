"""Detect discrete transit events from daily ephemeris.

Two event types, the cleanest and most discrete ones:

- INGRESS: the sign index changes between two consecutive days. A change of
  +1 is a forward ingress; -1 means the planet slipped back while retrograde
  (`backward=True`). The next forward ingress into a sign the planet had
  backed out of is marked `reentry=True`, so "first entry" can be studied on
  its own instead of being counted two or three times per pass.
- STATION_RETROGRADE / STATION_DIRECT: the retrograde flag flips. The flag
  comes from day-over-day longitude, and right at a station the motion is
  nearly zero, so a one- or two-day flicker is possible; runs shorter than
  MIN_STATE_DAYS are merged into their neighbours before detecting flips.

The Sun and Moon never go retrograde, so they only produce ingresses.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from orbit.core.types import Planet, SpeedClass, TransitEvent, TransitEventType
from orbit.data.ephemeris import ZODIAC_SIGNS
from orbit.analysis.series import PlanetSeries

MIN_STATE_DAYS = 3

SPEED_CLASS = {
    Planet.MOON: SpeedClass.LUNAR,
    Planet.SUN: SpeedClass.FAST,
    Planet.MERCURY: SpeedClass.FAST,
    Planet.VENUS: SpeedClass.FAST,
    Planet.MARS: SpeedClass.FAST,
    Planet.JUPITER: SpeedClass.SLOW,
    Planet.SATURN: SpeedClass.SLOW,
    Planet.URANUS: SpeedClass.SLOW,
    Planet.NEPTUNE: SpeedClass.SLOW,
    Planet.PLUTO: SpeedClass.SLOW,
}
STATION_PLANETS = [p for p in Planet if p not in (Planet.SUN, Planet.MOON)]


def _to_datetime(d: np.datetime64) -> datetime:
    return datetime.fromisoformat(str(d)).replace(tzinfo=timezone.utc)


def debounce(flags: np.ndarray, min_run: int = MIN_STATE_DAYS) -> np.ndarray:
    """Merge interior runs shorter than `min_run` into the run before them."""
    flags = flags.copy()
    changed = True
    while changed:
        changed = False
        edges = np.flatnonzero(np.diff(flags.astype(int))) + 1
        bounds = np.concatenate([[0], edges, [len(flags)]])
        for a, b in zip(bounds[1:-2], bounds[2:-1]):  # interior runs only
            if b - a < min_run:
                flags[a:b] = flags[a - 1]
                changed = True
                break
    return flags


def detect_ingresses(series: PlanetSeries) -> list[TransitEvent]:
    signs = series.sign_index
    change = np.flatnonzero(signs[1:] != signs[:-1]) + 1
    events = []
    backed_out_of: set[int] = set()  # signs the planet has retreated out of and not re-entered
    for i in change:
        old, new = int(signs[i - 1]), int(signs[i])
        backward = (new - old) % 12 == 11
        reentry = False
        if backward:
            backed_out_of.add(old)
        elif new in backed_out_of:
            reentry = True
            backed_out_of.discard(new)
        events.append(
            TransitEvent(
                planet=series.planet,
                event_type=TransitEventType.INGRESS,
                date=_to_datetime(series.dates[i]),
                from_state=ZODIAC_SIGNS[old],
                to_state=ZODIAC_SIGNS[new],
                backward=backward,
                reentry=reentry,
            )
        )
    return events


def detect_stations(series: PlanetSeries) -> list[TransitEvent]:
    if series.planet not in STATION_PLANETS:
        return []
    retro = debounce(series.retrograde)
    flips = np.flatnonzero(retro[1:] != retro[:-1]) + 1
    return [
        TransitEvent(
            planet=series.planet,
            event_type=TransitEventType.STATION_RETROGRADE if retro[i] else TransitEventType.STATION_DIRECT,
            date=_to_datetime(series.dates[i]),
            from_state="DIRECT" if retro[i] else "RETROGRADE",
            to_state="RETROGRADE" if retro[i] else "DIRECT",
        )
        for i in flips
    ]


def detect_all(planets: dict[Planet, PlanetSeries]) -> list[TransitEvent]:
    events = []
    for series in planets.values():
        events.extend(detect_ingresses(series))
        events.extend(detect_stations(series))
    return sorted(events, key=lambda e: (e.date, e.planet.value, e.event_type.value))


def event_label(e: TransitEvent) -> str:
    """Short human label, e.g. "MARS → Aries", "MERCURY Rx", "MERCURY D"."""
    if e.event_type == TransitEventType.INGRESS:
        suffix = " (back)" if e.backward else " (re-entry)" if e.reentry else ""
        return f"{e.planet.value} → {e.to_state}{suffix}"
    return f"{e.planet.value} {'Rx' if e.event_type == TransitEventType.STATION_RETROGRADE else 'D'}"
