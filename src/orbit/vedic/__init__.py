"""Vedic (Jyotish) astrology layer: sidereal positions, events and states.

All astro research in Orbit uses these rules only:

    zodiac.py   ayanamsa, rashis, nakshatras, grahas, dignities, drishti, combustion orbs
    sky.py      sidereal longitudes of the 9 grahas, sampled every 6 hours, plus exact-time search
    events.py   discrete events (ingresses, stations, yuti, drishti, asta, yuddha, lunations,
                eclipses, yogas, combinations), each with its exact moment
    patterns.py which events are grouped into testable patterns
    states.py   what is true on each day (for the chop track and the model's features)
"""
