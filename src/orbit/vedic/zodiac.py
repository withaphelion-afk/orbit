"""Jyotish rules used across the Vedic layer. Kept in one place so every
module (and every reader) sees the same definitions.

Zodiac: sidereal, Chitrapaksha (Lahiri family) ayanamsa: the star Chitra
(Spica) sits at exactly 0 degrees Tula (180 degrees). Positions are computed
in the J2000 ecliptic frame, which is fixed relative to the stars, so the
ayanamsa there is a single constant: Spica's J2000 ecliptic longitude minus
180 (about 23.84 degrees; the "of date" value grows with precession, ~24.2 in 2026).

Grahas: the 9 of Jyotish. Rahu is the Moon's mean north node; Ketu is always
exactly opposite. Uranus, Neptune and Pluto are not used.
"""

from __future__ import annotations

from orbit.core.types import Planet

RASHIS = ["Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya", "Tula", "Vrishchika", "Dhanu", "Makara", "Kumbha", "Meena"]
RASHI_EN = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha",
    "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada",
    "Uttara Bhadrapada", "Revati",
]
NAKSHATRA_SPAN = 360.0 / 27  # 13 deg 20 min

GRAHAS = [Planet.SUN, Planet.MOON, Planet.MARS, Planet.MERCURY, Planet.JUPITER, Planet.VENUS, Planet.SATURN, Planet.RAHU, Planet.KETU]
NODES = {Planet.RAHU, Planet.KETU}
STATION_GRAHAS = [Planet.MARS, Planet.MERCURY, Planet.JUPITER, Planet.VENUS, Planet.SATURN]  # can go vakri/margi
SLOW_GRAHAS = {Planet.JUPITER, Planet.SATURN, Planet.RAHU, Planet.KETU}
NAMES = {
    Planet.SUN: "Surya (Sun)", Planet.MOON: "Chandra (Moon)", Planet.MARS: "Mangal (Mars)", Planet.MERCURY: "Budh (Mercury)",
    Planet.JUPITER: "Guru (Jupiter)", Planet.VENUS: "Shukra (Venus)", Planet.SATURN: "Shani (Saturn)",
    Planet.RAHU: "Rahu", Planet.KETU: "Ketu",
}
SHORT = {
    Planet.SUN: "Surya", Planet.MOON: "Chandra", Planet.MARS: "Mangal", Planet.MERCURY: "Budh", Planet.JUPITER: "Guru",
    Planet.VENUS: "Shukra", Planet.SATURN: "Shani", Planet.RAHU: "Rahu", Planet.KETU: "Ketu",
}

# Uchcha (exaltation) and neecha (debilitation) rashis, by index.
EXALTATION = {Planet.SUN: 0, Planet.MOON: 1, Planet.MARS: 9, Planet.MERCURY: 5, Planet.JUPITER: 3, Planet.VENUS: 11, Planet.SATURN: 6}
DEBILITATION = {g: (r + 6) % 12 for g, r in EXALTATION.items()}

# Graha drishti, as houses counted from the graha's own rashi (1 = its own sign).
# Every graha aspects the 7th; Mars also the 4th and 8th, Jupiter the 5th and 9th,
# Saturn the 3rd and 10th. Rahu and Ketu are given the 5th and 9th (the common view).
SPECIAL_DRISHTI = {Planet.MARS: (4, 8), Planet.JUPITER: (5, 9), Planet.SATURN: (3, 10), Planet.RAHU: (5, 9), Planet.KETU: (5, 9)}

# Asta (combustion): within this many degrees of the Sun. Mercury and Venus use a
# smaller orb while vakri. The Moon's combustion is the amavasya, handled there.
COMBUSTION_ORB = {Planet.MARS: 17.0, Planet.MERCURY: 14.0, Planet.JUPITER: 11.0, Planet.VENUS: 10.0, Planet.SATURN: 15.0}
COMBUSTION_ORB_VAKRI = {Planet.MERCURY: 12.0, Planet.VENUS: 8.0}

# Graha yuddha (planetary war): two of these within this many degrees.
YUDDHA_GRAHAS = [Planet.MARS, Planet.MERCURY, Planet.JUPITER, Planet.VENUS, Planet.SATURN]
YUDDHA_ORB = 1.0

# Natural malefics and benefics (for the cluster combinations).
MALEFICS = {Planet.SATURN, Planet.MARS, Planet.RAHU, Planet.KETU, Planet.SUN}
BENEFICS = {Planet.JUPITER, Planet.VENUS, Planet.MERCURY}

# Eclipse limits: angular distance of the Sun (new moon) or Moon (full moon) from a node.
SOLAR_ECLIPSE_LIMIT = 18.0
LUNAR_ECLIPSE_LIMIT = 12.0


def rashi_label(i: int) -> str:
    return f"{RASHIS[i]} ({RASHI_EN[i]})"


def dignity(graha: Planet, rashi: int) -> str | None:
    if EXALTATION.get(graha) == rashi:
        return "uchcha (exalted)"
    if DEBILITATION.get(graha) == rashi:
        return "neecha (debilitated)"
    return None


def order(a: Planet, b: Planet) -> tuple[Planet, Planet]:
    """A fixed order for unordered pairs, so each pair has one pattern id."""
    return (a, b) if GRAHAS.index(a) < GRAHAS.index(b) else (b, a)


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
