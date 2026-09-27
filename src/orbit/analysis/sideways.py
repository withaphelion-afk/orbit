"""The chop track: which transit *states* coincide with sideways markets.

Asked as its own question, not as the inverse of the big-move analysis.
Instead of discrete events, this looks at states that last: "Mercury is
retrograde", "Saturn is in Pisces". For each state and horizon H:

    sideways rate in state = share of in-state days whose next H bars were SIDEWAYS
    base rate              = share of all days whose next H bars were SIDEWAYS

Significance uses the same circular shift, sliding the state's calendar
against the outcome series. The honest sample size is the number of distinct
*episodes* of the state, not the day count: 300 days of one Jupiter-in-Leo
stretch is one observation of Jupiter in Leo, not 300. States with fewer than
MIN_OCCURRENCES episodes are marked insufficient and not tested.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from orbit.config.settings import MIN_OCCURRENCES, MIN_SHIFT_GAP_DAYS
from orbit.core.types import Planet, SpeedClass
from orbit.data.ephemeris import ZODIAC_SIGNS
from orbit.analysis.outcomes import SIDEWAYS, HorizonOutcomes
from orbit.analysis.series import PlanetSeries, PriceSeries
from orbit.analysis.significance import episodes, shift_null_counts, shift_p_value
from orbit.analysis.transit_events import SPEED_CLASS, STATION_PLANETS, debounce


@dataclass
class StateTest:
    state_id: str
    description: str
    horizon: int
    days: int
    episodes: int
    rate: float
    base: float
    p: float | None


def state_masks(series: PriceSeries, planets: dict[Planet, PlanetSeries]) -> dict[str, tuple[str, np.ndarray]]:
    """{state_id: (description, bool mask over the asset's bars)}."""
    masks = {}
    for planet, ps in planets.items():
        if SPEED_CLASS[planet] == SpeedClass.LUNAR:
            continue  # a 2.5-day state says nothing about 10-20 day chop
        offset = (series.dates - ps.dates[0]).astype(int)
        inside = (offset >= 0) & (offset < len(ps.dates))
        idx = np.clip(offset, 0, len(ps.dates) - 1)
        name = planet.value.capitalize()
        if planet in STATION_PLANETS:
            retro = debounce(ps.retrograde)[idx] & inside
            masks[f"{planet.value}:RETROGRADE"] = (f"{name} retrograde", retro)
        signs = ps.sign_index[idx]
        for k, sign in enumerate(ZODIAC_SIGNS):
            masks[f"{planet.value}:IN:{sign}"] = (f"{name} in {sign}", (signs == k) & inside)
    return masks


def test_states(outcomes: HorizonOutcomes, masks: dict[str, tuple[str, np.ndarray]]) -> list[StateTest]:
    y = (outcomes.valid_codes == SIDEWAYS).astype(float)
    base = float(y.mean()) if len(y) else float("nan")
    tests = []
    for state_id, (desc, mask) in masks.items():
        m = mask[outcomes.start : outcomes.end]
        days = int(m.sum())
        eps = episodes(m)
        if days == 0:
            continue
        hits = int(y[m].sum())
        p = None
        if eps >= MIN_OCCURRENCES:
            null = shift_null_counts(y, m.astype(float), MIN_SHIFT_GAP_DAYS)
            p = shift_p_value(hits, null)
        tests.append(StateTest(state_id, desc, outcomes.horizon, days, eps, hits / days, base, p))
    return tests
