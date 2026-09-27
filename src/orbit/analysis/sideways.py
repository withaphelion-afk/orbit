"""The chop track: which transit *states* coincide with sideways markets.

Asked as its own question, not as the inverse of the big-move analysis.
Instead of discrete events, this looks at Vedic states that last: "Budh is
vakri", "Shani is in Meena", "Guru-Rahu yuti", "Kaal Sarp yoga". For each state and horizon H:

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
from orbit.analysis.outcomes import SIDEWAYS, HorizonOutcomes
from orbit.analysis.series import PriceSeries
from orbit.analysis.significance import episodes, shift_null_counts, shift_p_value
from orbit.vedic.states import States, on_dates


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


def state_masks(series: PriceSeries, states: States) -> dict[str, tuple[str, np.ndarray]]:
    """{state_id: (description, bool mask over the asset's bars)} for the Vedic
    states that last (Moon-driven states change too fast to say anything about
    10-20 day chop)."""
    return on_dates(states, series.dates, include_moon=False)


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
