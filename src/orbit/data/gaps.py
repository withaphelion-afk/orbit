"""Holes in stored price history.

Features and the transit research assume bars are evenly spaced, so a silent
hole (an exchange outage, a failed download) would shift every later window.
This finds the bars that are missing and cannot be explained by the market
being closed, and `assert_no_gaps` fails loudly when there are too many.
Nothing is ever filled in: an invented bar is an invented price.

Crypto trades around the clock, so every missing bar there is a hole. Silver
(spot XAG/USD) is closed from Friday evening to Sunday evening UTC, and for
a single day on exchange holidays; both are expected.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from orbit.core.types import Asset, Candle

# Tolerance: a handful of exchange outages is normal, a long hole or many holes is not.
MAX_UNEXPLAINED_FRACTION = 0.005  # of the bars the span should contain
MAX_GAP_BARS = {"1d": 3, "1h": 72}
# Silver also skips single exchange holidays (Good Friday, US holidays): a closure of up to one day.
SILVER_HOLIDAY_BARS = {"1d": 1, "1h": 24}


class DataGapError(RuntimeError):
    pass


def _step(timeframe: str) -> timedelta:
    return timedelta(days=1) if timeframe == "1d" else timedelta(hours=1)


def _closed(asset: Asset, timeframe: str, t: datetime) -> bool:
    """Is the market expected to have no bar at `t`?"""
    if asset != Asset.SILVER:
        return False
    if (t.month, t.day) in ((12, 25), (1, 1)):
        return True
    wd = t.weekday()  # Mon=0 .. Sun=6
    if timeframe == "1d":
        return wd >= 5  # the daily series may be weekday-only (stored Yahoo futures) or built from hourly bars
    return (wd == 4 and t.hour >= 21) or wd == 5 or (wd == 6 and t.hour < 23)


def find_gaps(asset: Asset, timeframe: str, candles: list[Candle]) -> dict:
    """{expected_bars, unexplained_bars, longest_gap_bars, gaps: [{start, bars}, ...]}.

    `gaps` lists up to 20 of the longest holes that are not explained by a market closure."""
    step = _step(timeframe)
    gaps: list[tuple[datetime, int]] = []
    unexplained = 0
    for a, b in zip(candles, candles[1:]):
        n_missing = int((b.timestamp - a.timestamp) / step) - 1
        if n_missing <= 0:
            continue
        run = 0
        for k in range(1, n_missing + 1):
            if _closed(asset, timeframe, a.timestamp + k * step):
                continue
            run += 1
        if asset == Asset.SILVER and run <= SILVER_HOLIDAY_BARS[timeframe]:
            continue
        if run:
            unexplained += run
            gaps.append((a.timestamp + step, run))
    expected = int((candles[-1].timestamp - candles[0].timestamp) / step) + 1 if candles else 0
    longest = sorted(gaps, key=lambda g: -g[1])[:20]
    return {
        "expected_bars": expected,
        "unexplained_bars": unexplained,
        "longest_gap_bars": longest[0][1] if longest else 0,
        "gaps": [{"start": s.isoformat(), "bars": n} for s, n in longest],
    }


def assert_no_gaps(asset: Asset, timeframe: str, candles: list[Candle]) -> dict:
    """Return the gap report, or raise DataGapError when the holes exceed the tolerance."""
    report = find_gaps(asset, timeframe, candles)
    too_many = report["unexplained_bars"] > MAX_UNEXPLAINED_FRACTION * max(report["expected_bars"], 1)
    too_long = report["longest_gap_bars"] > MAX_GAP_BARS[timeframe]
    if too_many or too_long:
        worst = ", ".join(f"{g['bars']} bars from {g['start'][:16]}" for g in report["gaps"][:3])
        raise DataGapError(
            f"{asset.value} {timeframe}: {report['unexplained_bars']} of {report['expected_bars']} bars missing "
            f"(longest hole {report['longest_gap_bars']}; worst: {worst}). Refusing to run analysis on a series with holes."
        )
    return report
