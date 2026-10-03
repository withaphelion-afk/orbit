"""NASA JPL's DE421 ephemeris kernel, loaded through Skyfield.

The kernel (de421.bsp, ~17 MB) is downloaded once into data/ephemeris_cache/
(and shared on the data branch), then read from disk. vedic/sky.py turns it
into sidereal positions; all of Orbit's astrology is computed there.
"""

from __future__ import annotations

from skyfield.api import Loader

from orbit.config.settings import DATA_DIR

_loader = Loader(DATA_DIR / "ephemeris_cache")
_ephemeris = None
_timescale = None


def _get_ephemeris():
    """(kernel, timescale), loaded once per process."""
    global _ephemeris, _timescale
    if _ephemeris is None:
        _ephemeris = _loader("de421.bsp")
        _timescale = _loader.timescale()
    return _ephemeris, _timescale
