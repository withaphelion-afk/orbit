from datetime import datetime, timedelta, timezone

import pytest

from orbit.core.types import Asset, Candle
from orbit.data.gaps import DataGapError, assert_no_gaps, find_gaps


def bars(start, n, step, skip=lambda t: False):
    out, t = [], start
    while len(out) < n:
        if not skip(t):
            out.append(Candle(asset=Asset.BTC, timestamp=t, open=1, high=1, low=1, close=1, volume=1))
        t += step
    return out


def with_asset(candles, asset):
    return [c.model_copy(update={"asset": asset}) for c in candles]


DAY, HOUR = timedelta(days=1), timedelta(hours=1)
T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)  # a Monday


def test_complete_crypto_series_passes():
    r = assert_no_gaps(Asset.BTC, "1d", bars(T0, 400, DAY))
    assert r["unexplained_bars"] == 0


def test_crypto_hole_is_found_and_fails_when_long():
    hole = lambda t: T0 + 100 * DAY <= t < T0 + 110 * DAY
    candles = bars(T0, 400, DAY, hole)
    assert find_gaps(Asset.BTC, "1d", candles)["longest_gap_bars"] == 10
    with pytest.raises(DataGapError):
        assert_no_gaps(Asset.BTC, "1d", candles)


def test_a_tiny_hole_is_tolerated_but_reported():
    candles = bars(T0, 3000, HOUR, lambda t: t == T0 + 500 * HOUR)
    r = assert_no_gaps(Asset.BTC, "1h", candles)
    assert r["unexplained_bars"] == 1


def test_silver_weekend_is_not_a_gap():
    weekend = lambda t: (t.weekday() == 4 and t.hour >= 22) or t.weekday() == 5 or (t.weekday() == 6 and t.hour < 22)
    candles = with_asset(bars(T0, 24 * 40, HOUR, weekend), Asset.SILVER)
    assert find_gaps(Asset.SILVER, "1h", candles)["unexplained_bars"] == 0
    daily = with_asset(bars(T0, 60, DAY, lambda t: t.weekday() >= 5), Asset.SILVER)
    assert_no_gaps(Asset.SILVER, "1d", daily)


def test_silver_hole_inside_a_trading_week_fails():
    hole = lambda t: T0 + 10 * DAY <= t < T0 + 14 * DAY  # Wed-Sat of week two (weekend part is excused)
    candles = with_asset(bars(T0, 400, DAY, lambda t: hole(t) or t.weekday() >= 5), Asset.SILVER)
    assert find_gaps(Asset.SILVER, "1d", candles)["unexplained_bars"] >= 2
