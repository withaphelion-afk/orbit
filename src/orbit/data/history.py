"""Full price history per asset and timeframe (daily and hourly), stitched
across venues, kept up to date incrementally.

Why stitch: Binance is the live venue for crypto, but it only lists BTC and
ETH from August 2017. The transit research needs every repeat of a slow
planet it can get, so older bars come from USD venues with long records:

    BTC     Bitstamp btcusd (2013+)  ->  Binance BTCUSDT (Aug 2017+)
    ETH     Coinbase ETH-USD (2016+) ->  Binance ETHUSDT (Aug 2017+)
    SOL     Binance SOLUSDT (Aug 2020+), no older venue needed
    SILVER  Dukascopy XAG/USD spot (May 2003+), hourly bars, UTC days built from them

The same venues serve daily ("1d") and hourly ("1h") bars. The join happens
at the newer venue's first bar. Before joining, the two venues' closes are
compared over their overlap; if they disagree by more than
STITCH_MAX_MEDIAN_DIFF the build fails loudly instead of quietly mixing two
different price series. Every bar keeps its `source`, and each build writes a
report (data/history_report.json).

Silver comes from a slow, throttled feed, so its full history is built from
a local cache that scripts/backfill_silver.py fills (and the runner tops up a
little each cycle). Until that cache is complete, a previously stored Yahoo
futures series is kept as is rather than replaced by a partial one.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from orbit.config.settings import DATA_DIR, HISTORY_START, STITCH_MAX_MEDIAN_DIFF, STITCH_OVERLAP_DAYS
from orbit.core.types import Asset, Candle
from orbit.data import binance, bitstamp, coinbase, dukascopy
from orbit.data.gaps import find_gaps
from orbit.data.dates import today_utc, utc_day
from orbit.data.storage import load_candles, save_candles

REPORT_PATH = DATA_DIR / "history_report.json"
REFRESH_OVERLAP_DAYS = 3  # re-fetch the last few days so the in-progress bar gets finalised
TIMEFRAMES = ("1d", "1h")
SILVER_TOPUP_SECONDS = 90  # how long one runner cycle may spend topping up the silver cache


class StitchError(RuntimeError):
    """Two venues disagree too much over their overlap to be joined."""


@dataclass(frozen=True)
class Venue:
    name: str
    fetch: Callable[[datetime, str], list[Candle]]  # (from day, timeframe) -> bars from then on


VENUES: dict[Asset, tuple[Venue | None, Venue]] = {
    # (older venue, primary venue)
    Asset.BTC: (
        Venue("bitstamp:btcusd", lambda start, tf: bitstamp.fetch_history(Asset.BTC, "btcusd", start, timeframe=tf)),
        Venue("binance:BTCUSDT", lambda start, tf: binance.fetch_history(Asset.BTC, start, timeframe=tf)),
    ),
    Asset.ETH: (
        Venue("coinbase:ETH-USD", lambda start, tf: coinbase.fetch_history(Asset.ETH, "ETH-USD", start, timeframe=tf)),
        Venue("binance:ETHUSDT", lambda start, tf: binance.fetch_history(Asset.ETH, start, timeframe=tf)),
    ),
    Asset.SOL: (None, Venue("binance:SOLUSDT", lambda start, tf: binance.fetch_history(Asset.SOL, start, timeframe=tf))),
}


def history_start(asset: Asset) -> datetime:
    return utc_day(HISTORY_START[asset.value])


def report_key(asset: Asset, timeframe: str) -> str:
    return asset.value if timeframe == "1d" else f"{asset.value}_{timeframe}"


def stitch(older: list[Candle], primary: list[Candle]) -> tuple[list[Candle], dict]:
    """Join `older` onto the front of `primary`. Pure function: raises StitchError
    when the venues disagree over their overlap, returns (candles, overlap stats)."""
    if not primary:
        raise StitchError("primary venue returned no bars")
    if not older:
        return primary, {"overlap_days": 0, "median_abs_diff": None, "max_abs_diff": None}
    primary_start = primary[0].timestamp
    overlap_end = primary_start + timedelta(days=STITCH_OVERLAP_DAYS)
    older_by_time = {c.timestamp: c for c in older}
    diffs = [
        abs(c.close / older_by_time[c.timestamp].close - 1)
        for c in primary
        if c.timestamp < overlap_end and c.timestamp in older_by_time
    ]
    if not diffs:
        raise StitchError(f"no overlapping bars between venues around {primary_start.date()}")
    median = statistics.median(diffs)
    if median > STITCH_MAX_MEDIAN_DIFF:
        raise StitchError(
            f"venues disagree by a median {median:.2%} over {len(diffs)} overlapping bars "
            f"(limit {STITCH_MAX_MEDIAN_DIFF:.0%}); refusing to stitch"
        )
    joined = [c for c in older if c.timestamp < primary_start] + primary
    return joined, {"overlap_days": len(diffs), "median_abs_diff": median, "max_abs_diff": max(diffs)}


def build_history(asset: Asset, timeframe: str = "1d") -> tuple[list[Candle], dict]:
    """Fetch and stitch the full history for one crypto asset (network heavy)."""
    start = history_start(asset)
    older_venue, primary_venue = VENUES[asset]
    primary = [c for c in primary_venue.fetch(start, timeframe) if c.timestamp >= start]
    older: list[Candle] = []
    if older_venue and primary and primary[0].timestamp > start:
        cutoff = primary[0].timestamp + timedelta(days=STITCH_OVERLAP_DAYS)
        older = [c for c in older_venue.fetch(start, timeframe) if start <= c.timestamp <= cutoff]
    candles, overlap = stitch(older, primary)
    return candles, _report(asset, timeframe, candles, overlap)


def update_history(asset: Asset, timeframe: str = "1d") -> tuple[list[Candle], dict | None]:
    """Bring stored history up to date. Does a full build when nothing usable is
    stored (no file, bars from before stitching existed, or a short legacy fetch)."""
    if asset == Asset.SILVER:
        return _update_silver(timeframe)
    stored = load_candles(asset, timeframe)
    needs_full = (
        not stored
        or not stored[0].source
        or stored[0].timestamp > history_start(asset) + timedelta(days=30)
    )
    if needs_full:
        candles, report = build_history(asset, timeframe)
        save_candles(candles, timeframe)
        _write_report(report_key(asset, timeframe), report)
        return candles, report

    _, primary_venue = VENUES[asset]
    since = utc_day(stored[-1].timestamp) - timedelta(days=REFRESH_OVERLAP_DAYS)
    candles = _merge(stored, primary_venue.fetch(since, timeframe))
    save_candles(candles, timeframe)
    return candles, None


# ---------------------------------------------------------------- silver


def silver_targets() -> list[dukascopy.Target]:
    """Every Dukascopy file silver's history needs, up to yesterday."""
    return dukascopy.targets(history_start(Asset.SILVER).date(), (today_utc() - timedelta(days=1)).date())


def silver_cache_complete() -> bool:
    return dukascopy.coverage(silver_targets())["complete"]


def rebuild_silver_from_cache() -> tuple[int, int]:
    """Build silver's daily and hourly history from the complete Dukascopy cache."""
    wanted = silver_targets()
    counts = []
    for timeframe in TIMEFRAMES:
        candles = dukascopy.candles(wanted, timeframe)
        save_candles(candles, timeframe)
        _write_report(report_key(Asset.SILVER, timeframe), _report(Asset.SILVER, timeframe, candles, {"overlap_days": 0, "median_abs_diff": None, "max_abs_diff": None}))
        counts.append(len(candles))
    return counts[0], counts[1]


def _update_silver(timeframe: str) -> tuple[list[Candle], dict | None]:
    stored = load_candles(Asset.SILVER, timeframe)
    wanted = silver_targets()
    dukascopy.download(wanted, give_up_after=SILVER_TOPUP_SECONDS)
    on_spot = bool(stored) and stored[-1].source == dukascopy.SOURCE
    if on_spot:
        # Normal case: re-aggregate the files covering the last few days.
        since = (stored[-1].timestamp - timedelta(days=REFRESH_OVERLAP_DAYS)).date()
        recent = [t for t in wanted if t.kind == "day" and t.start >= since or t.kind == "month" and t.start >= date(since.year, since.month, 1)]
        candles = _merge(stored, dukascopy.candles(recent, timeframe))
        save_candles(candles, timeframe)
        return candles, None
    if dukascopy.coverage(wanted)["complete"]:
        rebuild_silver_from_cache()
        return load_candles(Asset.SILVER, timeframe), load_report().get(report_key(Asset.SILVER, timeframe))
    return stored, None  # keep what's there (legacy Yahoo daily, or nothing hourly) until the cache is done


# ---------------------------------------------------------------- helpers


def _merge(stored: list[Candle], fresh: list[Candle]) -> list[Candle]:
    by_time = {c.timestamp: c for c in stored}
    for c in fresh:
        by_time[c.timestamp] = c
    return [by_time[t] for t in sorted(by_time)]


def _report(asset: Asset, timeframe: str, candles: list[Candle], overlap: dict) -> dict:
    sources: dict[str, dict] = {}
    for c in candles:
        s = sources.setdefault(c.source, {"source": c.source, "first": c.timestamp, "last": c.timestamp, "bars": 0})
        s["last"] = c.timestamp
        s["bars"] += 1
    step = timedelta(days=1) if timeframe == "1d" else timedelta(hours=1)
    expected = int((candles[-1].timestamp - candles[0].timestamp) / step) + 1 if candles else 0
    return {
        "asset": asset.value,
        "timeframe": timeframe,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "first": candles[0].timestamp.isoformat() if candles else None,
        "last": candles[-1].timestamp.isoformat() if candles else None,
        "bars": len(candles),
        # Crypto trades around the clock, so gaps there are real holes; silver skips weekends by design.
        "missing_bars": expected - len(candles),
        "gaps": find_gaps(asset, timeframe, candles) if candles else None,  # holes the market being closed doesn't explain
        "sources": [{**s, "first": s["first"].isoformat(), "last": s["last"].isoformat()} for s in sources.values()],
        **overlap,
    }


def _write_report(key: str, report: dict) -> None:
    existing = load_report()
    existing[key] = report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def load_report() -> dict:
    """The latest stitch report per asset and timeframe (empty until the first full build)."""
    if not REPORT_PATH.exists():
        return {}
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))
