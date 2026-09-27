"""What is true in the Vedic sky on each day, as 0/1 series.

Used by the chop track (which states coincide with sideways markets) and as
the Vedic features of the trained model. Read at 00:00 UTC each day, the same
instant a daily bar opens.

    {G}:VAKRI, {G}:ASTA          retrograde, combust
    {G}:IN:{rashi}               rashi placement (8 grahas; Ketu mirrors Rahu)
    {G}:UCHCHA, {G}:NEECHA       exalted, debilitated
    CHANDRA:NAKSHATRA:{name}     the Moon's nakshatra
    YUTI:.., DRISHTI..           relations in force
    YOGA:{name}                  Kaal Sarp, Kaal Amrit, Gajakesari, Shani-Mangal in force
    PAKSHA:SHUKLA                waxing moon
    GRAHAN:WINDOW                within 15 days of an eclipse
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from orbit.core.types import Planet, TransitEvent, TransitEventType
from orbit.vedic.util import debounce
from orbit.vedic import zodiac as z
from orbit.vedic.events import STATION_DEBOUNCE_SAMPLES, _relations, _yogas
from orbit.vedic.sky import Sky, load_sky, to_datetime, wrap

SAMPLES_PER_DAY = 4
ECLIPSE_WINDOW_DAYS = 15


@dataclass
class States:
    days: np.ndarray  # datetime64[D], one per day
    masks: dict[str, tuple[str, np.ndarray]]  # state_id -> (description, bool per day)
    moon_driven: set[str]  # states that change with the Moon (skipped by the chop track)


def build_states(sky: Sky | None = None, events: list[TransitEvent] | None = None) -> States:
    sky = sky or load_sky()
    daily = slice(0, None, SAMPLES_PER_DAY)  # the grid starts at 00:00 UTC
    start = to_datetime(sky.tt[0])
    n_days = len(sky.tt[daily])
    days = np.datetime64(start.replace(tzinfo=None).date(), "D") + np.arange(n_days)
    rashi = {g: (sky.lon[g] // 30).astype(int) for g in z.GRAHAS}
    vakri = {g: debounce(sky.spd[g] < 0, STATION_DEBOUNCE_SAMPLES) for g in z.STATION_GRAHAS}
    masks: dict[str, tuple[str, np.ndarray]] = {}
    moon: set[str] = set()

    def add(sid, desc, m, lunar=False):
        masks[sid] = (desc, np.asarray(m)[daily].astype(bool))
        if lunar:
            moon.add(sid)

    for g in z.STATION_GRAHAS:
        add(f"{g.value}:VAKRI", f"{z.SHORT[g]} vakri", vakri[g])
    sun = sky.lon[Planet.SUN]
    for g, orb in z.COMBUSTION_ORB.items():
        orbs = np.where(vakri[g], z.COMBUSTION_ORB_VAKRI.get(g, orb), orb)
        add(f"{g.value}:ASTA", f"{z.SHORT[g]} asta (combust)", np.abs(wrap(sky.lon[g] - sun)) < orbs)
    for g in z.GRAHAS:
        if g == Planet.KETU:
            continue
        lunar = g == Planet.MOON
        for r in range(12):
            add(f"{g.value}:IN:{z.RASHIS[r]}", f"{z.SHORT[g]} in {z.rashi_label(r)}", rashi[g] == r, lunar)
        if g in z.EXALTATION:
            add(f"{g.value}:UCHCHA", f"{z.SHORT[g]} uchcha (exalted)", rashi[g] == z.EXALTATION[g], lunar)
            add(f"{g.value}:NEECHA", f"{z.SHORT[g]} neecha (debilitated)", rashi[g] == z.DEBILITATION[g], lunar)
    nak = (sky.lon[Planet.MOON] // z.NAKSHATRA_SPAN).astype(int)
    for k, name in enumerate(z.NAKSHATRAS):
        add(f"CHANDRA:NAKSHATRA:{name}", f"Chandra in {name}", nak == k, True)

    _, rel = _relations(sky, rashi, vakri, {})
    for key, m in rel.items():
        if key[0] == "YUTI":
            a, b = key[1], key[2]
            sid, desc = f"YUTI:{a.value}+{b.value}", f"{z.SHORT[a]} with {z.SHORT[b]} (yuti)"
        elif key[1] == 7:
            a, b = key[2], key[3]
            sid, desc = f"DRISHTI7:{a.value}+{b.value}", f"{z.SHORT[a]} and {z.SHORT[b]} in 7th drishti"
        else:
            h, a, b = key[1], key[2], key[3]
            sid, desc = f"DRISHTI{h}:{a.value}>{b.value}", f"{z.SHORT[a]}'s {z.ordinal(h)} drishti on {z.SHORT[b]}"
        add(sid, desc, m, Planet.MOON in (a, b))
    _, yogas = _yogas(sky, rashi, rel, {})
    for name, m in yogas.items():
        add(f"YOGA:{name}", name.replace("_", " ").title() + " yoga in force", m, name in ("GAJAKESARI", "KAAL_SARP", "KAAL_AMRIT"))
    elong = (sky.lon[Planet.MOON] - sun) % 360
    add("PAKSHA:SHUKLA", "Shukla paksha (waxing moon)", elong < 180, True)

    window = np.zeros(n_days, bool)
    for e in events or []:
        if e.event_type in (TransitEventType.SOLAR_ECLIPSE, TransitEventType.LUNAR_ECLIPSE):
            d = (np.datetime64(e.date.replace(tzinfo=None).date(), "D") - days[0]).astype(int)
            window[max(0, d - ECLIPSE_WINDOW_DAYS) : d + ECLIPSE_WINDOW_DAYS + 1] = True
    masks["GRAHAN:WINDOW"] = ("Within 15 days of an eclipse", window)
    return States(days=days, masks=masks, moon_driven=moon)


def on_dates(states: States, dates: np.ndarray, include_moon: bool = True) -> dict[str, tuple[str, np.ndarray]]:
    """The states re-indexed onto an asset's bar dates (datetime64[D])."""
    idx = (np.asarray(dates, dtype="datetime64[D]") - states.days[0]).astype(int)
    inside = (idx >= 0) & (idx < len(states.days))
    idx = np.clip(idx, 0, len(states.days) - 1)
    return {
        sid: (desc, m[idx] & inside)
        for sid, (desc, m) in states.masks.items()
        if include_moon or sid not in states.moon_driven
    }


def today_utc_index(states: States) -> int:
    today = np.datetime64(datetime.now(timezone.utc).date(), "D")
    return int((today - states.days[0]).astype(int))
