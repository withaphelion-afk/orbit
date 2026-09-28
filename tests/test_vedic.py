"""Vedic layer checks against published Jyotish dates (Lahiri / Chitrapaksha)."""

from datetime import datetime, timezone

import numpy as np
import pytest

from orbit.core.types import Planet, TransitEventType
from orbit.vedic import zodiac as z
from orbit.vedic.events import detect
from orbit.vedic.sky import ayanamsa_j2000, build_sky, sidereal_longitude, tt_of
from orbit.vedic.util import debounce

UTC = timezone.utc


def test_ayanamsa_is_chitrapaksha():
    # Spica at 0 Tula; about 23.84 degrees in the J2000 frame (~24.2 "of date" in 2026).
    assert 23.8 < ayanamsa_j2000() < 23.9
    spica_lon = ayanamsa_j2000() + 180.0
    assert int(spica_lon // 30) == 7 or abs(spica_lon - 203.8) < 0.2  # sanity on the constant itself


@pytest.mark.parametrize(
    "graha, when, rashi",
    [
        (Planet.SATURN, datetime(2026, 9, 27, tzinfo=UTC), "Meena"),
        (Planet.JUPITER, datetime(2026, 9, 27, tzinfo=UTC), "Karka"),
        (Planet.RAHU, datetime(2026, 9, 27, tzinfo=UTC), "Kumbha"),
        (Planet.KETU, datetime(2026, 9, 27, tzinfo=UTC), "Simha"),
        (Planet.SUN, datetime(2026, 1, 20, tzinfo=UTC), "Makara"),  # after Makar Sankranti (~14 Jan)
    ],
)
def test_sidereal_positions(graha, when, rashi):
    lon = sidereal_longitude(graha, tt_of(when))[0]
    assert z.RASHIS[int(lon // 30)] == rashi


@pytest.fixture(scope="module")
def events_2024_2026():
    sky = build_sky(datetime(2024, 1, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC))
    return detect(sky)


def _first(events, etype, planet=None, to_state=None, year=None):
    for e in events:
        if e.event_type == etype and (planet is None or e.planet == planet) and (to_state is None or e.to_state == to_state)                 and (year is None or e.exact_time.year == year):
            return e
    return None


def test_known_ingresses(events_2024_2026):
    sat = _first(events_2024_2026, TransitEventType.INGRESS, Planet.SATURN, "Meena")
    assert sat.exact_time.date().isoformat() == "2025-03-29"
    rahu = _first(events_2024_2026, TransitEventType.INGRESS, Planet.RAHU, "Kumbha")
    assert rahu.exact_time.date().isoformat() == "2025-05-18"
    sankranti = _first(events_2024_2026, TransitEventType.INGRESS, Planet.SUN, "Makara", 2025)
    assert sankranti.exact_time.date().isoformat() == "2025-01-14"  # Makar Sankranti
    guru_back = [e for e in events_2024_2026 if e.event_type == TransitEventType.INGRESS and e.planet == Planet.JUPITER and e.backward]
    assert any(e.exact_time.date().isoformat() == "2025-12-05" and e.to_state == "Mithuna" for e in guru_back)


def test_known_eclipses(events_2024_2026):
    solar = [e.exact_time.date().isoformat() for e in events_2024_2026 if e.event_type == TransitEventType.SOLAR_ECLIPSE]
    lunar = [e.exact_time.date().isoformat() for e in events_2024_2026 if e.event_type == TransitEventType.LUNAR_ECLIPSE]
    for d in ("2024-04-08", "2024-10-02", "2025-03-29", "2025-09-21", "2026-02-17", "2026-08-12"):
        assert d in solar
    for d in ("2024-03-25", "2024-09-18", "2025-03-14", "2025-09-07", "2026-03-03", "2026-08-28"):
        assert d in lunar


def test_every_event_has_an_exact_moment_and_label(events_2024_2026):
    assert all(e.exact_time is not None and e.label for e in events_2024_2026)
    assert all(e.date == e.exact_time.replace(hour=0, minute=0, second=0) for e in events_2024_2026)


def test_exact_ingress_is_on_the_boundary(events_2024_2026):
    e = _first(events_2024_2026, TransitEventType.INGRESS, Planet.SATURN, "Meena")
    lon = sidereal_longitude(Planet.SATURN, tt_of(e.exact_time))[0]
    assert abs(((lon - 330.0 + 540) % 360) - 180) < 1e-3


def test_rahu_ketu_are_opposite_and_have_no_7th_drishti(events_2024_2026):
    t = tt_of(datetime(2026, 1, 1, tzinfo=UTC))
    assert abs(((sidereal_longitude(Planet.KETU, t) - sidereal_longitude(Planet.RAHU, t))[0] % 360) - 180) < 1e-9
    assert not any(e.event_type == TransitEventType.DRISHTI and e.to_state == "7" and {e.planet, e.other_planet} & z.NODES
                   for e in events_2024_2026)


def test_drishti_rules():
    assert z.drishti_houses(Planet.SATURN) == (7, 3, 10)
    assert z.drishti_houses(Planet.MARS) == (7, 4, 8)
    assert z.drishti_houses(Planet.JUPITER) == (7, 5, 9)
    assert z.drishti_houses(Planet.VENUS) == (7,)
    assert z.dignity(Planet.SATURN, z.RASHIS.index("Tula")) == "uchcha (exalted)"
    assert z.dignity(Planet.MARS, z.RASHIS.index("Karka")) == "neecha (debilitated)"
    assert [z.ordinal(n) for n in (3, 4, 5, 10, 11, 21)] == ["3rd", "4th", "5th", "10th", "11th", "21st"]


def test_debounce_removes_station_flicker():
    flags = np.array([False] * 10 + [True] + [False] * 2 + [True] * 20 + [False] * 10)
    assert debounce(flags, 3).tolist().count(True) == 20
