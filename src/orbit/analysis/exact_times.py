"""The exact moment of each transit, to the second, from the JPL ephemeris.

Daily detection (transit_events.py) only says which day a sign change or
station fell on. The hourly drill-down needs the moment itself, so each event
is refined by bisection on Skyfield positions, done for all of a planet's
events at once (one vectorised position call per halving step):

- ingress: when ecliptic longitude crosses the sign boundary (a multiple of
  30 degrees), searched in the 24 hours before the day it was detected on;
- station: when the planet's apparent motion reverses (longitudinal speed
  crosses zero), searched in a window around the detected day.

28 halvings of a one-day window leave ~0.3 seconds of uncertainty, far below
the hourly bars this feeds. A station whose speed doesn't change sign inside
its window is left without an exact time rather than guessed.

Refined events are also re-dated to the UTC day of their exact moment, so the
daily analysis measures from the day the transit really happened.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from orbit.core.types import Planet, TransitEvent, TransitEventType
from orbit.data.dates import utc_day
from orbit.data.ephemeris import BODY_NAMES, ZODIAC_SIGNS, _get_ephemeris

ITERATIONS = 28
SPEED_STEP_DAYS = 1 / 24  # finite-difference step for speed near a station
STATION_WINDOW = (-3.0, 1.0)  # days relative to the detected day


def _jd(dts: list[datetime]) -> np.ndarray:
    _, ts = _get_ephemeris()
    return np.array([ts.from_datetime(d).tt for d in dts])


def _longitude(planet: Planet, tt: np.ndarray) -> np.ndarray:
    eph, ts = _get_ephemeris()
    t = ts.tt_jd(tt)
    _, lon, _ = eph["earth"].at(t).observe(eph[BODY_NAMES[planet]]).apparent().ecliptic_latlon()
    return np.atleast_1d(lon.degrees)


def _wrap(x: np.ndarray) -> np.ndarray:
    return (x + 540.0) % 360.0 - 180.0


def _bisect(f, lo: np.ndarray, hi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised bisection for sign changes of f on [lo, hi]. Returns (root, bracketed?)."""
    f_lo = f(lo)
    f_hi = f(hi)
    ok = np.sign(f_lo) != np.sign(f_hi)
    for _ in range(ITERATIONS):
        mid = (lo + hi) / 2
        f_mid = f(mid)
        left = np.sign(f_mid) == np.sign(f_lo)
        lo = np.where(left, mid, lo)
        f_lo = np.where(left, f_mid, f_lo)
        hi = np.where(left, hi, mid)
    return (lo + hi) / 2, ok


def _to_datetime(tt: float) -> datetime:
    _, ts = _get_ephemeris()
    return ts.tt_jd(tt).utc_datetime().replace(microsecond=0).astimezone(timezone.utc)


def refine(events: list[TransitEvent], since: datetime | None = None) -> list[TransitEvent]:
    """Copies of `events` with `exact_time` filled in and `date` moved to that moment's
    UTC day, sorted by date (events before `since` are left as they are)."""
    out = list(events)
    by_planet: dict[tuple[Planet, bool], list[int]] = {}
    for i, e in enumerate(events):
        if since is not None and e.date < since:
            continue
        by_planet.setdefault((e.planet, e.event_type == TransitEventType.INGRESS), []).append(i)

    for (planet, is_ingress), idx in by_planet.items():
        day = _jd([events[i].date for i in idx])
        if is_ingress:
            boundary = np.array(
                [
                    30.0 * (ZODIAC_SIGNS.index(events[i].from_state) if events[i].backward else ZODIAC_SIGNS.index(events[i].to_state))
                    for i in idx
                ]
            )
            f = lambda tt, b=boundary: _wrap(_longitude(planet, tt) - b)
            root, ok = _bisect(f, day - 1.0, day)
        else:
            def f(tt):
                return _wrap(_longitude(planet, tt + SPEED_STEP_DAYS) - _longitude(planet, tt - SPEED_STEP_DAYS))

            root, ok = _bisect(f, day + STATION_WINDOW[0], day + STATION_WINDOW[1])
        for k, i in enumerate(idx):
            if ok[k]:
                exact = _to_datetime(float(root[k]))
                # Re-date the event to the UTC day it actually happened. Daily detection
                # compares midnight positions, so it sees an ingress on the next day and
                # a station up to two days late.
                out[i] = events[i].model_copy(update={"exact_time": exact, "date": utc_day(exact)})
    return sorted(out, key=lambda e: (e.date, e.planet.value, e.event_type.value))


def shift(events: list[TransitEvent], days: int) -> list[TransitEvent]:
    """Move events (and their exact times) by whole days, for placebo calendars."""
    delta = timedelta(days=days)
    return [
        e.model_copy(update={"date": e.date + delta, "exact_time": e.exact_time + delta if e.exact_time else None})
        for e in events
    ]
