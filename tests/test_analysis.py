from datetime import datetime, timedelta, timezone
from math import comb

import numpy as np
import pytest

from orbit.analysis import confidence
from orbit.analysis.outcomes import BIG_DOWN, BIG_UP, SIDEWAYS, label_outcomes
from orbit.analysis.series import PriceSeries
from orbit.analysis.significance import (
    benjamini_hochberg,
    episodes,
    hypergeom_sf,
    shift_null_counts,
    shift_p_value,
)
from orbit.core.types import Asset, Candle, ConfidenceLabel, Planet, TransitEventType
from orbit.data.history import StitchError, stitch


def _random_walk(n=3000, seed=1) -> PriceSeries:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    high = close * (1 + np.abs(rng.normal(0, 0.01, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.01, n)))
    dates = np.arange(np.datetime64("2010-01-01"), np.datetime64("2010-01-01") + np.timedelta64(n, "D"), dtype="datetime64[D]")
    return PriceSeries(Asset.BTC, dates, close.copy(), high, low, close)


# ---------------------------------------------------------------- outcomes


def test_outcome_labels_hit_their_target_rates():
    o = label_outcomes(_random_walk(), 10)
    codes = o.valid_codes
    assert abs(np.mean(codes == BIG_UP) - 0.15) < 0.01
    assert abs(np.mean(codes == BIG_DOWN) - 0.15) < 0.01
    assert 0 < np.mean(codes == SIDEWAYS) < 0.25
    assert o.end == len(o.codes) - 10  # the last horizon's worth of bars has no label yet


# ---------------------------------------------------------------- significance


def test_shift_null_matches_brute_force():
    rng = np.random.default_rng(3)
    y = (rng.random(200) < 0.2).astype(float)
    e = np.zeros(200)
    e[rng.choice(200, 15, replace=False)] = 1
    fast = shift_null_counts(y, e, min_gap=10)
    brute = [int(y[(np.flatnonzero(e) + k) % 200].sum()) for k in range(10, 191)]
    assert fast.tolist() == brute


def test_hypergeom_matches_exact_enumeration():
    L, K, n = 12, 5, 4
    exact = sum(comb(K, x) * comb(L - K, n - x) for x in range(2, 5)) / comb(L, n)
    assert hypergeom_sf(2, L, K, n) == pytest.approx(exact)


def test_benjamini_hochberg_known_values():
    q = benjamini_hochberg([0.01, 0.04, 0.03, 0.2])
    assert q == pytest.approx([0.04, 0.0533333, 0.0533333, 0.2], rel=1e-4)


def test_episodes_counts_runs():
    assert episodes(np.array([0, 1, 1, 0, 1, 0, 0, 1], dtype=bool)) == 3


def _pattern_p(o, event_rel) -> tuple[float, float]:
    y = (o.valid_codes == BIG_UP).astype(float)
    ind = np.zeros(len(y))
    ind[event_rel] = 1
    hits = int(y[event_rel].sum())
    return hits / len(event_rel), shift_p_value(hits, shift_null_counts(y, ind, 30))


def test_method_finds_a_planted_effect():
    """Power check: if half of a pattern's occurrences really precede big up-moves,
    the test must flag it strongly."""
    o = label_outcomes(_random_walk(seed=7), 10)
    codes = o.valid_codes
    rng = np.random.default_rng(7)
    ups = rng.choice(np.flatnonzero(codes == BIG_UP), 20, replace=False)
    others = rng.choice(np.flatnonzero(codes != BIG_UP), 20, replace=False)
    rate, p = _pattern_p(o, np.sort(np.concatenate([ups, others])))
    assert rate == pytest.approx(0.5)
    assert p < 1e-4
    assert confidence.label(40, rate, 0.15, p, p * 50) in (ConfidenceLabel.STRONG, ConfidenceLabel.MODERATE)


def test_random_events_are_not_flagged():
    o = label_outcomes(_random_walk(seed=11), 10)
    rng = np.random.default_rng(11)
    ps = [_pattern_p(o, np.sort(rng.choice(len(o.valid_codes), 30, replace=False)))[1] for _ in range(200)]
    # Under the null, about 5% of p-values fall below 0.05; allow sampling noise.
    assert np.mean(np.array(ps) < 0.05) < 0.1


def test_small_samples_are_never_labelled():
    assert confidence.label(8, 0.9, 0.15, 1e-6, 1e-5) == ConfidenceLabel.INSUFFICIENT_DATA


# ---------------------------------------------------------------- stitching


def _candles(start_day: int, closes, source) -> list[Candle]:
    base = datetime(2017, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(asset=Asset.BTC, timestamp=base + timedelta(days=start_day + i), open=c, high=c, low=c, close=c, volume=1, source=source)
        for i, c in enumerate(closes)
    ]


def test_stitch_joins_at_primary_start():
    older = _candles(0, [100.0] * 20, "old")
    primary = _candles(10, [100.5] * 20, "new")
    joined, report = stitch(older, primary)
    assert [c.source for c in joined[:10]] == ["old"] * 10
    assert [c.source for c in joined[10:]] == ["new"] * 20
    assert report["overlap_days"] == 10


def test_stitch_refuses_disagreeing_venues():
    with pytest.raises(StitchError):
        stitch(_candles(0, [100.0] * 20, "old"), _candles(10, [120.0] * 20, "new"))


# ---------------------------------------------------------------- timing

from datetime import datetime as _dt  # noqa: E402

from orbit.analysis import exact_times, timing  # noqa: E402
from orbit.core.types import TransitEvent  # noqa: E402


def test_shift_moves_exact_times_too():
    e = TransitEvent(planet=Planet.SUN, event_type=TransitEventType.INGRESS, date=_dt(2020, 1, 2, tzinfo=timezone.utc), from_state="Dhanu", to_state="Makara", exact_time=_dt(2020, 1, 1, 10, 30, tzinfo=timezone.utc))
    [s] = exact_times.shift([e], 10)
    assert s.date == e.date + timedelta(days=10) and s.exact_time == e.exact_time + timedelta(days=10)


def _hourly(prices, start="2021-01-04T00"):
    close = np.array(prices, dtype=float)
    dates = np.arange(np.datetime64(start), np.datetime64(start) + np.timedelta64(len(close), "h"), dtype="datetime64[h]")
    return PriceSeries(Asset.BTC, dates, close.copy(), close.copy(), close.copy(), close)


def test_hour_index_maps_closed_market_to_next_bar():
    s = _hourly([100.0] * 10)
    assert timing.hour_index(s, _dt(2021, 1, 4, 3, 45, tzinfo=timezone.utc)) == 3
    assert timing.hour_index(s, _dt(2021, 1, 3, 20, 0, tzinfo=timezone.utc)) == 0  # 4h before the first bar
    assert timing.hour_index(s, _dt(2020, 12, 30, 0, 0, tzinfo=timezone.utc)) is None  # too far before


def test_path_metrics_times_the_move_from_the_exact_moment():
    # Flat for 80 hours, then +1% per hour for 10 hours, then flat.
    prices = [100.0] * 80 + [100.0 * 1.01**k for k in range(1, 11)] + [100.0 * 1.01**10] * 30
    s = _hourly(prices)
    m = timing.path_metrics(s, 75, direction=1, window_hours=48, atr_fraction=0.03)
    assert m["pre_move_return"] == pytest.approx(0.0)
    assert m["hours_to_move"] == 7  # bar 82 is the first +3% (1.01^3 - 1 ≈ 3.03%)
    assert m["hours_to_peak"] == 14  # the rally tops out at bar 89
    assert m["peak_return"] == pytest.approx(1.01**10 - 1)


def test_romano_wolf_is_never_looser_than_the_raw_p_and_keeps_order():
    import numpy as np

    from orbit.analysis.significance import romano_wolf, shift_p_value

    rng = np.random.default_rng(1)
    nulls = [rng.poisson(20, 400) for _ in range(6)]
    observed = [45, 24, 20, 19, 22, 30]  # one clear effect, one mild, the rest noise
    adj = romano_wolf(observed, nulls)
    raw = [shift_p_value(o, n) for o, n in zip(observed, nulls)]
    assert all(a >= r - 1e-12 for a, r in zip(adj, raw))
    assert adj[0] == min(adj) and adj[0] < 0.05
    assert all(a > 0.05 for a in adj[2:4])


def test_romano_wolf_standardises_unlike_tests():
    import numpy as np

    from orbit.analysis.significance import romano_wolf

    rng = np.random.default_rng(2)
    small = rng.poisson(3, 500)  # rare target: counts tiny
    big = rng.poisson(200, 500)  # common target: counts huge, and noisier in absolute terms
    adj = romano_wolf([12, 205], [small, big])
    assert adj[0] < 0.05 < adj[1]  # 12 vs mean 3 is a real effect; 205 vs mean 200 is noise
