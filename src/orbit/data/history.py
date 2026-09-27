"""Full price history per asset, stitched across venues, kept up to date
incrementally.

Why stitch: Binance is the live venue for crypto, but it only lists BTC and
ETH from August 2017. The transit research needs every repeat of a slow
planet it can get, so older bars come from USD venues with long records:

    BTC     Bitstamp btcusd (2013+)  ->  Binance BTCUSDT (Aug 2017+)
    ETH     Coinbase ETH-USD (2016+) ->  Binance ETHUSDT (Aug 2017+)
    SOL     Binance SOLUSDT (Aug 2020+), no older venue needed
    SILVER  Yahoo SI=F (Aug 2000+)

The join happens at the newer venue's first bar. Before joining, the two
venues' closes are compared over their overlap; if they disagree by more than
STITCH_MAX_MEDIAN_DIFF the build fails loudly instead of quietly mixing two
different price series. Every bar keeps its `source`, and each build writes a
report (data/history_report.json) describing exactly what was joined.

After the first build, `update_history` only fetches bars since the last
stored day from the primary venue, so the hourly runner stays cheap.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from orbit.config.settings import DATA_DIR, HISTORY_START, STITCH_MAX_MEDIAN_DIFF, STITCH_OVERLAP_DAYS, TIMEFRAME
from orbit.core.types import Asset, Candle
from orbit.data import binance, bitstamp, coinbase, silver
from orbit.data.dates import utc_day
from orbit.data.storage import load_candles, save_candles

REPORT_PATH = DATA_DIR / "history_report.json"
REFRESH_OVERLAP_DAYS = 3  # re-fetch the last few days so the in-progress bar gets finalised


class StitchError(RuntimeError):
    """Two venues disagree too much over their overlap to be joined."""


@dataclass(frozen=True)
class Venue:
    name: str
    fetch: Callable[[datetime], list[Candle]]  # all bars from the given day onward


VENUES: dict[Asset, tuple[Venue | None, Venue]] = {
    # (older venue, primary venue)
    Asset.BTC: (
        Venue("bitstamp:btcusd", lambda start: bitstamp.fetch_history(Asset.BTC, "btcusd", start)),
        Venue("binance:BTCUSDT", lambda start: binance.fetch_history(Asset.BTC, start)),
    ),
    Asset.ETH: (
        Venue("coinbase:ETH-USD", lambda start: coinbase.fetch_history(Asset.ETH, "ETH-USD", start)),
        Venue("binance:ETHUSDT", lambda start: binance.fetch_history(Asset.ETH, start)),
    ),
    Asset.SOL: (None, Venue("binance:SOLUSDT", lambda start: binance.fetch_history(Asset.SOL, start))),
    Asset.SILVER: (None, Venue("yahoo:SI=F", lambda start: silver.fetch_history(start))),
}


def history_start(asset: Asset) -> datetime:
    return utc_day(HISTORY_START[asset.value])


def stitch(older: list[Candle], primary: list[Candle]) -> tuple[list[Candle], dict]:
    """Join `older` onto the front of `primary`. Pure function: raises StitchError
    when the venues disagree over their overlap, returns (candles, overlap stats)."""
    if not primary:
        raise StitchError("primary venue returned no bars")
    if not older:
        return primary, {"overlap_days": 0, "median_abs_diff": None, "max_abs_diff": None}
    primary_start = primary[0].timestamp
    overlap_end = primary_start + timedelta(days=STITCH_OVERLAP_DAYS)
    older_by_day = {c.timestamp: c for c in older}
    diffs = [
        abs(c.close / older_by_day[c.timestamp].close - 1)
        for c in primary
        if c.timestamp < overlap_end and c.timestamp in older_by_day
    ]
    if not diffs:
        raise StitchError(f"no overlapping days between venues around {primary_start.date()}")
    median = statistics.median(diffs)
    if median > STITCH_MAX_MEDIAN_DIFF:
        raise StitchError(
            f"venues disagree by a median {median:.2%} over {len(diffs)} overlapping days "
            f"(limit {STITCH_MAX_MEDIAN_DIFF:.0%}); refusing to stitch"
        )
    joined = [c for c in older if c.timestamp < primary_start] + primary
    return joined, {"overlap_days": len(diffs), "median_abs_diff": median, "max_abs_diff": max(diffs)}


def build_history(asset: Asset) -> tuple[list[Candle], dict]:
    """Fetch and stitch the full history for one asset (network heavy; used for the first build)."""
    start = history_start(asset)
    older_venue, primary_venue = VENUES[asset]
    primary = [c for c in primary_venue.fetch(start) if c.timestamp >= start]
    older: list[Candle] = []
    if older_venue and primary and primary[0].timestamp > start:
        older = [c for c in older_venue.fetch(start) if start <= c.timestamp <= primary[0].timestamp + timedelta(days=STITCH_OVERLAP_DAYS)]
    candles, overlap = stitch(older, primary)
    return candles, _report(asset, candles, overlap)


def update_history(asset: Asset) -> tuple[list[Candle], dict | None]:
    """Bring stored history up to date. Does a full build when nothing usable is
    stored (no file, bars from before stitching existed, or a short legacy fetch)."""
    stored = load_candles(asset, TIMEFRAME)
    needs_full = (
        not stored
        or any(not c.source for c in stored[:1])
        or stored[0].timestamp > history_start(asset) + timedelta(days=30)
    )
    if needs_full:
        candles, report = build_history(asset)
        save_candles(candles, TIMEFRAME)
        _write_report(asset, report)
        return candles, report

    _, primary_venue = VENUES[asset]
    since = stored[-1].timestamp - timedelta(days=REFRESH_OVERLAP_DAYS)
    fresh = primary_venue.fetch(since)
    by_day = {c.timestamp: c for c in stored}
    for c in fresh:
        by_day[c.timestamp] = c
    candles = [by_day[d] for d in sorted(by_day)]
    save_candles(candles, TIMEFRAME)
    return candles, None


def _report(asset: Asset, candles: list[Candle], overlap: dict) -> dict:
    sources: dict[str, dict] = {}
    for c in candles:
        s = sources.setdefault(c.source, {"source": c.source, "first": c.timestamp, "last": c.timestamp, "bars": 0})
        s["last"] = c.timestamp
        s["bars"] += 1
    expected_days = (candles[-1].timestamp - candles[0].timestamp).days + 1 if candles else 0
    return {
        "asset": asset.value,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "first": candles[0].timestamp.isoformat() if candles else None,
        "last": candles[-1].timestamp.isoformat() if candles else None,
        "bars": len(candles),
        # Crypto trades every day, so gaps there are real holes; silver skips weekends by design.
        "missing_calendar_days": expected_days - len(candles),
        "sources": [{**s, "first": s["first"].isoformat(), "last": s["last"].isoformat()} for s in sources.values()],
        **overlap,
    }


def _write_report(asset: Asset, report: dict) -> None:
    existing = load_report()
    existing[asset.value] = report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def load_report() -> dict:
    """The latest stitch report per asset (empty until the first full build)."""
    if not REPORT_PATH.exists():
        return {}
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))
