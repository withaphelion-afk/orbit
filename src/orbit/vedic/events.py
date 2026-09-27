"""Every discrete Vedic event, each with its exact moment.

Detection works on the 6-hour sample grid (sky.py); every event is then pinned
to the second, either by bisection on the defining quantity or, for events
that start when a graha changes rashi (yuti, drishti, yogas), by taking the
exact moment of that ingress.

Events:
- INGRESS: a graha enters a new rashi (Rahu's ingress is also Ketu's, into the
  opposite rashi, so Ketu gets no separate ingress). `backward` marks a vakri
  graha slipping back into the previous rashi; `reentry` the forward ingress
  that follows one.
- NAKSHATRA_INGRESS: Chandra and Surya entering each of the 27 nakshatras.
- STATION_RETROGRADE / STATION_DIRECT: Mars, Mercury, Jupiter, Venus, Saturn
  turning vakri / margi (6-hour flicker at the station is debounced).
- YUTI: two grahas come into the same rashi.
- DRISHTI: a graha starts to aspect another by rashi: the 7th for everyone
  (recorded once per pair, as it's mutual), plus Mars 4/8, Jupiter 5/9,
  Saturn 3/10 and Rahu/Ketu 5/9. A 7th aspect with a node is the same thing as
  a yuti with the opposite node, so it's recorded as that yuti only.
- COMBUSTION: a graha comes within its asta orb of the Sun.
- GRAHA_YUDDHA: two of Mars..Saturn come within 1 degree.
- AMAVASYA / PURNIMA: new and full moon; SOLAR_ECLIPSE / LUNAR_ECLIPSE when
  the Sun (new moon) or Moon (full moon) is within the eclipse limit of a node.
- YOGA: Kaal Sarp (all seven grahas on one side of the Rahu-Ketu axis) and its
  mirror Kaal Amrit, Gajakesari (Guru in a kendra from Chandra), Shani-Mangal
  (any yuti or drishti between Saturn and Mars).
- CLUSTER: three or more malefic (or benefic) relations beginning within 7 days.
"""

from __future__ import annotations

import json
from datetime import timezone

import numpy as np

from orbit.config.settings import DATA_DIR
from orbit.core.types import Planet, TransitEvent, TransitEventType
from orbit.vedic.util import debounce
from orbit.data.dates import utc_day
from orbit.vedic import zodiac as z
from orbit.vedic.sky import CACHE as SKY_CACHE
from orbit.vedic.sky import Sky, bisect, load_sky, sidereal_longitude, speed, to_datetime, wrap

EVENTS_CACHE = DATA_DIR / "vedic" / "events.json"
STATION_DEBOUNCE_SAMPLES = 8  # 2 days
CLUSTER_WINDOW_DAYS = 7
CLUSTER_MIN = 3
CLUSTER_GAP_DAYS = 30
T = TransitEventType


def _ev(graha, etype, tt, from_state, to_state, label, **kw) -> TransitEvent:
    exact = to_datetime(tt)
    return TransitEvent(planet=graha, event_type=etype, date=utc_day(exact), from_state=from_state, to_state=to_state,
                        exact_time=exact, label=label, **kw)


def _ingresses(sky: Sky, rashi: dict) -> tuple[list[TransitEvent], dict]:
    """Rashi ingresses, and {(graha, sample): exact tt} for the relations that start with them."""
    events, when = [], {}
    for g in z.GRAHAS:
        if g == Planet.KETU:
            continue
        r = rashi[g]
        idx = np.flatnonzero(r[1:] != r[:-1]) + 1
        if not len(idx):
            continue
        frm, to = r[idx - 1], r[idx]
        step = (to - frm) % 12
        node = g in z.NODES
        # Nodes move backwards through the zodiac as their normal motion.
        backward = (step == 1) if node else (step == 11)
        boundary = np.where(step == 1, to, frm) * 30.0
        roots, ok = bisect(lambda tt, b=boundary: wrap(sidereal_longitude(g, tt) - b), sky.tt[idx - 1], sky.tt[idx])
        backed_out: set[int] = set()
        for k, i in enumerate(idx):
            tt = roots[k] if ok[k] else sky.tt[i]
            when[(g, int(i))] = tt
            if node:
                when[(Planet.KETU, int(i))] = tt
            f, t_ = int(frm[k]), int(to[k])
            reentry = False
            if backward[k]:
                backed_out.add(f)
            elif t_ in backed_out:
                reentry = True
                backed_out.discard(t_)
            if node:
                label = f"Rahu enters {z.rashi_label(t_)}, Ketu {z.rashi_label((t_ + 6) % 12)}"
            else:
                dig = z.dignity(g, t_)
                label = f"{z.SHORT[g]} enters {z.rashi_label(t_)}" + (f", {dig}" if dig else "") + (" (vakri, back)" if backward[k] else "")
            events.append(_ev(g, T.INGRESS, tt, z.RASHIS[f], z.RASHIS[t_], label, backward=bool(backward[k]), reentry=reentry))
    return events, when


def _nakshatras(sky: Sky) -> list[TransitEvent]:
    events = []
    for g in (Planet.MOON, Planet.SUN):
        n = (sky.lon[g] // z.NAKSHATRA_SPAN).astype(int)
        idx = np.flatnonzero(n[1:] != n[:-1]) + 1
        to = n[idx]
        roots, ok = bisect(lambda tt, b=to * z.NAKSHATRA_SPAN: wrap(sidereal_longitude(g, tt) - b), sky.tt[idx - 1], sky.tt[idx])
        for k, i in enumerate(idx):
            name = z.NAKSHATRAS[int(to[k])]
            events.append(_ev(g, T.NAKSHATRA_INGRESS, roots[k] if ok[k] else sky.tt[i], z.NAKSHATRAS[int(n[i - 1])], name,
                              f"{z.SHORT[g]} enters {name} nakshatra"))
    return events


def _stations(sky: Sky, vakri: dict) -> list[TransitEvent]:
    events = []
    for g in z.STATION_GRAHAS:
        v = vakri[g]
        idx = np.flatnonzero(v[1:] != v[:-1]) + 1
        if not len(idx):
            continue
        roots, ok = bisect(lambda tt: speed(g, tt), sky.tt[idx] - 1.5, sky.tt[idx] + 1.5)
        for k, i in enumerate(idx):
            turning_vakri = bool(v[i])
            events.append(_ev(g, T.STATION_RETROGRADE if turning_vakri else T.STATION_DIRECT, roots[k] if ok[k] else sky.tt[i],
                              "MARGI" if turning_vakri else "VAKRI", "VAKRI" if turning_vakri else "MARGI",
                              f"{z.SHORT[g]} turns {'vakri (retrograde)' if turning_vakri else 'margi (direct)'}"))
    return events


def _starts(mask: np.ndarray) -> np.ndarray:
    return np.flatnonzero(mask[1:] & ~mask[:-1]) + 1


def _trigger(when: dict, a: Planet, b: Planet, i: int, sky: Sky) -> float:
    """Exact moment a rashi-based relation began: the later of the two grahas' ingresses into this interval."""
    ts = [when[(g, i)] for g in (a, b) if (g, i) in when]
    return max(ts) if ts else float(sky.tt[i])


def _relations(sky: Sky, rashi: dict, vakri: dict, when: dict) -> tuple[list[TransitEvent], dict]:
    """Yuti and drishti starts, plus each relation's daily mask (reused by yogas and states)."""
    events, masks = [], {}

    def vakri_at(g, i):
        return bool(vakri[g][i]) if g in vakri else False

    grahas = z.GRAHAS
    for ai, a in enumerate(grahas):
        for b in grahas[ai + 1:]:
            if {a, b} == z.NODES:
                continue
            same = rashi[a] == rashi[b]
            masks[("YUTI", a, b)] = same
            for i in _starts(same):
                retro = vakri_at(a, i) or vakri_at(b, i)
                label = f"{z.SHORT[a]} and {z.SHORT[b]} together in {z.rashi_label(int(rashi[a][i]))} (yuti)"
                events.append(_ev(a, T.YUTI, _trigger(when, a, b, i, sky), "", z.RASHIS[int(rashi[a][i])], label,
                                  other_planet=b, retro_involved=retro))
            if a in z.NODES or b in z.NODES:
                continue  # a 7th aspect with a node is the yuti with the opposite node
            opposite = (rashi[b] - rashi[a]) % 12 == 6
            masks[("DRISHTI", 7, a, b)] = opposite
            for i in _starts(opposite):
                retro = vakri_at(a, i) or vakri_at(b, i)
                events.append(_ev(a, T.DRISHTI, _trigger(when, a, b, i, sky), "", "7",
                                  f"{z.SHORT[a]} and {z.SHORT[b]} in mutual 7th drishti (samsaptak)", other_planet=b, retro_involved=retro))
    for a, houses in z.SPECIAL_DRISHTI.items():
        for b in grahas:
            if b == a or {a, b} == z.NODES:
                continue
            for h in houses:
                aspects = (rashi[b] - rashi[a]) % 12 == h - 1
                masks[("DRISHTI", h, a, b)] = aspects
                for i in _starts(aspects):
                    retro = vakri_at(a, i) or vakri_at(b, i)
                    events.append(_ev(a, T.DRISHTI, _trigger(when, a, b, i, sky), "", str(h),
                                      f"{z.SHORT[a]} casts its {z.ordinal(h)} drishti on {z.SHORT[b]}", other_planet=b, retro_involved=retro))
    return events, masks


def _threshold_starts(sky: Sky, inside: np.ndarray, f, etype, graha, other, label_of) -> list[TransitEvent]:
    idx = _starts(inside)
    if not len(idx):
        return []
    roots, ok = bisect(f, sky.tt[idx - 1], sky.tt[idx])
    return [_ev(graha, etype, roots[k] if ok[k] else sky.tt[i], "", "", label_of(i), other_planet=other) for k, i in enumerate(idx)]


def _combustion_and_war(sky: Sky, vakri: dict) -> list[TransitEvent]:
    events = []
    sun = sky.lon[Planet.SUN]
    for g, orb in z.COMBUSTION_ORB.items():
        sep = np.abs(wrap(sky.lon[g] - sun))
        orbs = np.where(vakri.get(g, np.zeros(len(sky), bool)), z.COMBUSTION_ORB_VAKRI.get(g, orb), orb)
        inside = sep < orbs
        orb_now = float(orb)
        events += _threshold_starts(
            sky, inside,
            lambda tt, g=g, o=orb_now: np.abs(wrap(sidereal_longitude(g, tt) - sidereal_longitude(Planet.SUN, tt))) - o,
            T.COMBUSTION, g, Planet.SUN, lambda i, g=g: f"{z.SHORT[g]} becomes asta (combust) near the Sun",
        )
    for ai, a in enumerate(z.YUDDHA_GRAHAS):
        for b in z.YUDDHA_GRAHAS[ai + 1:]:
            inside = np.abs(wrap(sky.lon[a] - sky.lon[b])) < z.YUDDHA_ORB
            events += _threshold_starts(
                sky, inside,
                lambda tt, a=a, b=b: np.abs(wrap(sidereal_longitude(a, tt) - sidereal_longitude(b, tt))) - z.YUDDHA_ORB,
                T.GRAHA_YUDDHA, a, b, lambda i, a=a, b=b: f"Graha yuddha: {z.SHORT[a]} and {z.SHORT[b]} within 1 degree",
            )
    return events


def _lunations(sky: Sky) -> list[TransitEvent]:
    events = []
    elong = (sky.lon[Planet.MOON] - sky.lon[Planet.SUN]) % 360
    for target, etype in ((0.0, T.AMAVASYA), (180.0, T.PURNIMA)):
        d = wrap(elong - target)
        idx = np.flatnonzero((d[:-1] < 0) & (d[1:] >= 0) & (np.abs(d[:-1]) < 90)) + 1
        roots, ok = bisect(
            lambda tt, t0=target: wrap(sidereal_longitude(Planet.MOON, tt) - sidereal_longitude(Planet.SUN, tt) - t0),
            sky.tt[idx - 1], sky.tt[idx],
        )
        for k, i in enumerate(idx):
            tt = roots[k] if ok[k] else sky.tt[i]
            rahu = sidereal_longitude(Planet.RAHU, tt)[0]
            body = Planet.SUN if etype == T.AMAVASYA else Planet.MOON
            lon = sidereal_longitude(body, tt)[0]
            to_node = min(abs(wrap(lon - rahu)), abs(wrap(lon - rahu - 180)))
            nak = z.NAKSHATRAS[int(sidereal_longitude(Planet.MOON, tt)[0] // z.NAKSHATRA_SPAN)]
            name = "Amavasya (new moon)" if etype == T.AMAVASYA else "Purnima (full moon)"
            events.append(_ev(Planet.MOON, etype, tt, "", nak, f"{name} in {nak}"))
            limit = z.SOLAR_ECLIPSE_LIMIT if etype == T.AMAVASYA else z.LUNAR_ECLIPSE_LIMIT
            if to_node < limit:
                kind = T.SOLAR_ECLIPSE if etype == T.AMAVASYA else T.LUNAR_ECLIPSE
                label = f"{'Surya' if kind == T.SOLAR_ECLIPSE else 'Chandra'} grahan ({'solar' if kind == T.SOLAR_ECLIPSE else 'lunar'} eclipse) in {nak}"
                events.append(_ev(body, kind, tt, "", nak, label))
    return events


def _yogas(sky: Sky, rashi: dict, masks: dict, when: dict) -> tuple[list[TransitEvent], dict]:
    events, yoga_masks = [], {}
    # Shani-Mangal: any yuti or drishti between Saturn and Mars.
    sm = np.zeros(len(sky), bool)
    for key, m in masks.items():
        if {Planet.SATURN, Planet.MARS} <= set(k for k in key if isinstance(k, Planet)):
            sm |= m
    yoga_masks["SHANI_MANGAL"] = sm
    for i in _starts(sm):
        events.append(_ev(Planet.SATURN, T.YOGA, _trigger(when, Planet.SATURN, Planet.MARS, i, sky), "", "SHANI_MANGAL",
                          "Shani-Mangal yoga begins (Saturn and Mars in yuti or drishti)", other_planet=Planet.MARS))
    # Gajakesari: Guru in a kendra (1, 4, 7, 10) from Chandra.
    gk = np.isin((rashi[Planet.JUPITER] - rashi[Planet.MOON]) % 12, (0, 3, 6, 9))
    yoga_masks["GAJAKESARI"] = gk
    for i in _starts(gk):
        events.append(_ev(Planet.JUPITER, T.YOGA, _trigger(when, Planet.JUPITER, Planet.MOON, i, sky), "", "GAJAKESARI",
                          "Gajakesari yoga begins (Guru in a kendra from Chandra)", other_planet=Planet.MOON))
    # Kaal Sarp / Kaal Amrit: all seven grahas on one side of the Rahu-Ketu axis.
    rahu = sky.lon[Planet.RAHU]
    seven = [Planet.SUN, Planet.MOON, Planet.MARS, Planet.MERCURY, Planet.JUPITER, Planet.VENUS, Planet.SATURN]
    d = np.array([(sky.lon[g] - rahu) % 360 for g in seven])
    for name, inside, label in (
        ("KAAL_SARP", np.all(d > 180, axis=0), "Kaal Sarp yoga begins (all grahas between Rahu and Ketu)"),
        ("KAAL_AMRIT", np.all(d < 180, axis=0), "Kaal Amrit yoga begins (all grahas between Ketu and Rahu)"),
    ):
        yoga_masks[name] = inside
        for i in _starts(inside):
            # The yoga forms when the last graha crosses the axis; find which and pin it.
            crossing = [k for k in range(len(seven)) if (d[k, i - 1] > 180) != (d[k, i] > 180)]
            tt = float(sky.tt[i])
            if crossing:
                k = crossing[0]
                g = seven[k]
                axis = 180.0 if abs(d[k, i] - 180) < 90 else 0.0  # crossed Ketu (180) or Rahu (0)
                roots, ok = bisect(lambda x, g=g, a=axis: wrap(sidereal_longitude(g, x) - sidereal_longitude(Planet.RAHU, x) - a),
                                   [sky.tt[i - 1]], [sky.tt[i]])
                tt = float(roots[0]) if ok[0] else tt
            events.append(_ev(Planet.RAHU, T.YOGA, tt, "", name, label, other_planet=Planet.KETU))
    return events, yoga_masks


def _clusters(relations: list[TransitEvent]) -> list[TransitEvent]:
    events = []
    for kind, members in (("MALEFIC", z.MALEFICS), ("BENEFIC", z.BENEFICS)):
        starts = sorted(
            (e for e in relations if e.event_type in (T.YUTI, T.DRISHTI) and e.planet in members and e.other_planet in members),
            key=lambda e: e.exact_time,
        )
        last = None
        for k in range(CLUSTER_MIN - 1, len(starts)):
            first, now = starts[k - CLUSTER_MIN + 1].exact_time, starts[k].exact_time
            if (now - first).days < CLUSTER_WINDOW_DAYS and (last is None or (now - last).days >= CLUSTER_GAP_DAYS):
                last = now
                names = ", ".join(e.label for e in starts[k - CLUSTER_MIN + 1 : k + 1])
                events.append(TransitEvent(planet=starts[k].planet, event_type=T.CLUSTER, date=utc_day(now), from_state="", to_state=kind,
                                           exact_time=now, label=f"{kind.title()} cluster: {names}"))
    return events


def detect(sky: Sky) -> list[TransitEvent]:
    rashi = {g: (sky.lon[g] // 30).astype(int) for g in z.GRAHAS}
    vakri = {g: debounce(sky.spd[g] < 0, STATION_DEBOUNCE_SAMPLES) for g in z.STATION_GRAHAS}
    ingresses, when = _ingresses(sky, rashi)
    relations, masks = _relations(sky, rashi, vakri, when)
    yogas, _ = _yogas(sky, rashi, masks, when)
    events = (
        ingresses + _nakshatras(sky) + _stations(sky, vakri) + relations + _combustion_and_war(sky, vakri)
        + _lunations(sky) + yogas + _clusters(relations)
    )
    return sorted(events, key=lambda e: (e.exact_time, e.event_type.value, e.planet.value))


def load_events() -> list[TransitEvent]:
    """All Vedic events, cached alongside the sky grid they were detected on."""
    sky = load_sky()
    if EVENTS_CACHE.exists() and EVENTS_CACHE.stat().st_mtime >= SKY_CACHE.stat().st_mtime:
        return [TransitEvent.model_validate(e) for e in json.loads(EVENTS_CACHE.read_text(encoding="utf-8"))]
    events = detect(sky)
    EVENTS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    EVENTS_CACHE.write_text(json.dumps([e.model_dump(mode="json") for e in events]), encoding="utf-8")
    return events
