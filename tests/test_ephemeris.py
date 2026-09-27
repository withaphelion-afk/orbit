from datetime import datetime, timezone

from orbit.core.types import Planet
from orbit.data.ephemeris import compute_snapshot, longitude_to_sign


def test_longitude_to_sign_boundaries():
    assert longitude_to_sign(0) == "Aries"
    assert longitude_to_sign(29.9) == "Aries"
    assert longitude_to_sign(30) == "Taurus"
    assert longitude_to_sign(359.9) == "Pisces"


def test_jupiter_in_leo_on_known_date():
    # Real-world Jupiter entered Leo in mid-2026 — a fixed regression check
    # against the ephemeris data, not just a live computation.
    snapshot = compute_snapshot(Planet.JUPITER, datetime(2026, 9, 27, tzinfo=timezone.utc))
    assert snapshot.sign == "Leo"
    assert snapshot.retrograde is False
