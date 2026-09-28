"""Which Vedic events are grouped into testable patterns.

Each event belongs to one or more patterns (a pattern_id plus description).
The hypothesis list is simply every pattern that occurs, written out before
any test runs (analysis/playbook.py).

    {G}:RASHI              graha changes rashi (first entries only)
    {G}:RASHI:{rashi}      graha enters one rashi (exaltation / debilitation named)
    {G}:NAKSHATRA:{name}   Chandra or Surya enters one nakshatra
    SUN:NAKSHATRA          Surya changes nakshatra (every ~13 days)
    {G}:VAKRI / {G}:MARGI  graha turns retrograde / direct
    YUTI:{A}+{B}           two grahas come into one rashi (named yogas where they apply)
    DRISHTI7:{A}+{B}       mutual 7th aspect (samsaptak)
    DRISHTI{h}:{A}>{B}     A casts its special h-th aspect on B
    ...|VAKRI              the same yuti / drishti, begun while one of them is vakri (combination)
    {G}:ASTA               graha becomes combust
    YUDDHA:{A}+{B}         planetary war
    AMAVASYA, PURNIMA, GRAHAN:SURYA, GRAHAN:CHANDRA
    YOGA:{name}            Kaal Sarp, Kaal Amrit, Gajakesari, Shani-Mangal begin
    CLUSTER:MALEFIC / CLUSTER:BENEFIC  three such relations begin within a week

Backward ingresses and re-entries are recorded but not tested, so one pass
through a rashi counts once.

Speed class (which forward horizons are measured): anything driven by the
Moon is LUNAR; anything involving only Guru, Shani, Rahu and Ketu is SLOW;
the rest FAST.
"""

from __future__ import annotations

from orbit.core.types import Planet, SpeedClass, TransitEvent, TransitEventType
from orbit.vedic import zodiac as z

T = TransitEventType

YUTI_YOGAS = {
    frozenset({Planet.JUPITER, Planet.RAHU}): "Guru-Chandal yoga",
    frozenset({Planet.JUPITER, Planet.KETU}): "Guru-Chandal yoga (with Ketu)",
    frozenset({Planet.SUN, Planet.RAHU}): "Grahan yoga (Surya with Rahu)",
    frozenset({Planet.SUN, Planet.KETU}): "Grahan yoga (Surya with Ketu)",
    frozenset({Planet.MOON, Planet.RAHU}): "Grahan yoga (Chandra with Rahu)",
    frozenset({Planet.MOON, Planet.KETU}): "Grahan yoga (Chandra with Ketu)",
    frozenset({Planet.MARS, Planet.SATURN}): "Shani-Mangal yuti",
    frozenset({Planet.MARS, Planet.RAHU}): "Angarak yoga (Mangal with Rahu)",
}
YOGA_NAMES = {
    "KAAL_SARP": "Kaal Sarp yoga begins",
    "KAAL_AMRIT": "Kaal Amrit yoga begins",
    "GAJAKESARI": "Gajakesari yoga begins (Guru in a kendra from Chandra)",
    "SHANI_MANGAL": "Shani-Mangal yoga begins (any yuti or drishti between Saturn and Mars)",
}


def speed_class(e: TransitEvent) -> SpeedClass:
    involved = {e.planet} | ({e.other_planet} if e.other_planet else set())
    if Planet.MOON in involved and e.event_type not in (T.AMAVASYA, T.PURNIMA, T.SOLAR_ECLIPSE, T.LUNAR_ECLIPSE):
        return SpeedClass.LUNAR
    if e.event_type == T.YOGA and e.to_state in ("KAAL_SARP", "KAAL_AMRIT"):
        return SpeedClass.FAST  # it forms and breaks as the Moon crosses the axis
    if involved <= z.SLOW_GRAHAS and e.event_type in (T.INGRESS, T.YUTI, T.DRISHTI, T.STATION_RETROGRADE, T.STATION_DIRECT):
        return SpeedClass.SLOW
    return SpeedClass.FAST


def keys(e: TransitEvent) -> list[tuple[str, str]]:
    """(pattern_id, description) for every pattern this event belongs to."""
    g, o = e.planet, e.other_planet
    name = z.NAMES[g]
    if e.event_type == T.INGRESS:
        if e.backward or e.reentry:
            return []
        r = z.RASHIS.index(e.to_state)
        if g == Planet.RAHU:
            return [("RAHU:RASHI", "Rahu-Ketu change rashi"), (f"RAHU:RASHI:{e.to_state}", e.label)]
        dig = z.dignity(g, r)
        return [(f"{g.value}:RASHI", f"{name} changes rashi"),
                (f"{g.value}:RASHI:{e.to_state}", f"{name} enters {z.rashi_label(r)}" + (f", {dig}" if dig else ""))]
    if e.event_type == T.NAKSHATRA_INGRESS:
        out = [(f"{g.value}:NAKSHATRA:{e.to_state}", f"{name} enters {e.to_state} nakshatra")]
        if g == Planet.SUN:
            out.append(("SUN:NAKSHATRA", "Surya changes nakshatra"))
        return out
    if e.event_type == T.STATION_RETROGRADE:
        return [(f"{g.value}:VAKRI", f"{name} turns vakri (retrograde)")]
    if e.event_type == T.STATION_DIRECT:
        return [(f"{g.value}:MARGI", f"{name} turns margi (direct)")]
    if e.event_type in (T.YUTI, T.DRISHTI):
        a, b = (z.order(g, o) if e.event_type == T.YUTI or e.to_state == "7" else (g, o))
        if e.event_type == T.YUTI:
            pid = f"YUTI:{a.value}+{b.value}"
            yoga = YUTI_YOGAS.get(frozenset({a, b}))
            desc = f"{z.SHORT[a]} and {z.SHORT[b]} come into one rashi (yuti)" + (f": {yoga}" if yoga else "")
        elif e.to_state == "7":
            pid = f"DRISHTI7:{a.value}+{b.value}"
            desc = f"{z.SHORT[a]} and {z.SHORT[b]} in mutual 7th drishti (samsaptak)"
        else:
            pid = f"DRISHTI{e.to_state}:{a.value}>{b.value}"
            desc = f"{z.SHORT[a]} casts its {z.ordinal(int(e.to_state))} drishti on {z.SHORT[b]}"
        out = [(pid, desc)]
        if e.retro_involved:
            out.append((f"{pid}|VAKRI", f"{desc}, begun while one of them is vakri"))
        return out
    if e.event_type == T.COMBUSTION:
        return [(f"{g.value}:ASTA", f"{name} becomes asta (combust)")]
    if e.event_type == T.GRAHA_YUDDHA:
        a, b = z.order(g, o)
        return [(f"YUDDHA:{a.value}+{b.value}", f"Graha yuddha between {z.SHORT[a]} and {z.SHORT[b]}")]
    if e.event_type == T.AMAVASYA:
        return [("AMAVASYA", "Amavasya (new moon)")]
    if e.event_type == T.PURNIMA:
        return [("PURNIMA", "Purnima (full moon)")]
    if e.event_type == T.SOLAR_ECLIPSE:
        return [("GRAHAN:SURYA", "Surya grahan (solar eclipse)")]
    if e.event_type == T.LUNAR_ECLIPSE:
        return [("GRAHAN:CHANDRA", "Chandra grahan (lunar eclipse)")]
    if e.event_type == T.YOGA:
        return [(f"YOGA:{e.to_state}", YOGA_NAMES.get(e.to_state, e.to_state))]
    if e.event_type == T.CLUSTER:
        return [(f"CLUSTER:{e.to_state}", f"{e.to_state.title()} cluster: 3+ {e.to_state.lower()} relations begin within a week")]
    return []
