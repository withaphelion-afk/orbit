"""Spot silver (XAG/USD) history from Dukascopy's free public datafeed.

Why Dukascopy: Yahoo only serves the last 730 days of hourly silver, while
Dukascopy has XAG/USD back to 2003 with no account or key. It is *spot*
silver, not the SI=F futures contract, so there are no contract-roll jumps.
All silver research (daily and hourly) uses this one instrument.

Two kinds of LZMA-compressed candle files are read, both BID prices:

    datafeed/XAGUSD/{year}/{month-1:02}/BID_candles_hour_1.bi5         hourly bars, one file per month
    datafeed/XAGUSD/{year}/{month-1:02}/{day:02}/BID_candles_min_1.bi5 1-minute bars, one file per day

Completed months come from the monthly hourly file (~280 files for the whole
history); the current, unfinished month is assembled from daily minute files.
Each record is 24 bytes, big-endian: seconds since the file's start (int32),
then open, close, low, high as int32 in thousandths of a dollar, then volume
(float32). Bars with zero volume are filler for closed markets and are dropped.
Daily bars are UTC days built from the hourly bars.

The server throttles bulk readers (timeouts and HTTP 503 after a burst), so
downloads are paced, cached under data/cache/dukascopy/, and resumable:
re-running skips every file already on disk and backs off when the server
pushes back. Files the feed genuinely doesn't have are remembered as empty.
"""

from __future__ import annotations

import lzma
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import requests

from orbit.config.settings import DATA_DIR
from orbit.core.types import Asset, Candle
from orbit.data.http import USER_AGENT

INSTRUMENT = "XAGUSD"
PRICE_SCALE = 1000.0
BASE = "https://datafeed.dukascopy.com/datafeed/" + INSTRUMENT
CACHE_DIR = DATA_DIR / "cache" / "dukascopy" / INSTRUMENT
SOURCE = f"dukascopy:{INSTRUMENT}"
RECORD = np.dtype([("sec", ">i4"), ("open", ">i4"), ("close", ">i4"), ("low", ">i4"), ("high", ">i4"), ("volume", ">f4")])

# Minimum traded hours for a UTC day to count as a daily bar. The Sunday
# evening reopen (from ~22:00 UTC) leaves a stub of a couple of hours that
# would otherwise appear as a tiny, misleading daily candle.
MIN_DAILY_HOURS = 6
PUBLISH_GRACE_DAYS = 10  # a missing file younger than this is retried later, not marked empty


class Throttled(RuntimeError):
    """The server refused or timed out; wait and try again later."""


@dataclass(frozen=True)
class Target:
    """One file to fetch: a completed month of hourly bars, or one day of minute bars."""

    start: date
    kind: str  # "month" or "day"

    @property
    def url(self) -> str:
        if self.kind == "month":
            return f"{BASE}/{self.start.year}/{self.start.month - 1:02d}/BID_candles_hour_1.bi5"
        return f"{BASE}/{self.start.year}/{self.start.month - 1:02d}/{self.start.day:02d}/BID_candles_min_1.bi5"

    @property
    def path(self) -> Path:
        name = f"{self.start:%Y-%m}.hour.bi5" if self.kind == "month" else f"{self.start:%Y-%m-%d}.min.bi5"
        return CACHE_DIR / f"{self.start:%Y}" / name

    @property
    def empty_marker(self) -> Path:
        return self.path.with_suffix(".empty")

    def cached(self) -> bool:
        return self.path.exists() or self.empty_marker.exists()

    def settled(self, today: date) -> bool:
        """Old enough that a missing file means "no data", not "not published yet"."""
        end = date(self.start.year + (self.start.month == 12), self.start.month % 12 + 1, 1) if self.kind == "month" else self.start
        return (today - end).days > PUBLISH_GRACE_DAYS


def targets(start: date, end: date) -> list[Target]:
    """Files covering [start, end]: monthly hourly files for months that are over,
    daily minute files (Saturdays skipped) for the part of `end`'s month so far."""
    out: list[Target] = []
    current_month = date(end.year, end.month, 1)
    m = date(start.year, start.month, 1)
    while m < current_month:
        out.append(Target(m, "month"))
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    d = max(start, current_month)
    while d <= end:
        if d.weekday() != 5:
            out.append(Target(d, "day"))
        d += timedelta(days=1)
    return out


def fetch(target: Target, session: requests.Session) -> bytes | None:
    try:
        r = session.get(target.url, timeout=(10, 40))
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise Throttled(type(exc).__name__) from exc
    if r.status_code in (429, 500, 502, 503, 504):
        raise Throttled(f"HTTP {r.status_code}")
    if r.status_code == 404 or (r.status_code == 200 and not r.content):
        return None
    r.raise_for_status()
    return r.content


def download(
    wanted: list[Target],
    pace_seconds: float = 1.0,
    max_backoff_seconds: float = 300,
    on_progress: Callable[[int, int, str], None] | None = None,
    give_up_after: float | None = None,
) -> dict[str, int]:
    """Fetch every target not already cached. Returns counts. Safe to interrupt and re-run.

    `give_up_after` (seconds) stops early, leaving the rest for next time, so a
    throttled feed can never stall a runner cycle.
    """
    def new_session() -> requests.Session:
        s = requests.Session()
        s.headers["User-Agent"] = USER_AGENT
        return s

    session = new_session()
    started = time.monotonic()
    todo = [t for t in wanted if not t.cached()]
    counts = {"requested": len(todo), "saved": 0, "empty": 0, "not_published": 0, "throttled": 0}
    today = date.today()
    backoff = 5.0
    i = 0
    while i < len(todo):
        if give_up_after is not None and time.monotonic() - started > give_up_after:
            break
        target = todo[i]
        try:
            content = fetch(target, session)
        except Throttled as exc:
            counts["throttled"] += 1
            if on_progress:
                on_progress(i, len(todo), f"server busy ({exc}); waiting {backoff:.0f}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff_seconds)
            session = new_session()  # a fresh connection often gets through
            continue
        backoff = 5.0
        target.path.parent.mkdir(parents=True, exist_ok=True)
        if content is None:
            if target.settled(today):
                target.empty_marker.touch()
                counts["empty"] += 1
            else:
                counts["not_published"] += 1  # ask again next time
        else:
            tmp = target.path.with_suffix(".part")
            tmp.write_bytes(content)
            tmp.replace(target.path)
            counts["saved"] += 1
        i += 1
        if on_progress:
            on_progress(i, len(todo), f"{target.start:%Y-%m-%d} {target.kind}")
        time.sleep(pace_seconds)
    counts["remaining"] = len(todo) - i
    return counts


def _records(target: Target) -> np.ndarray | None:
    if not target.path.exists():
        return None
    raw = lzma.decompress(target.path.read_bytes())
    n = len(raw) // RECORD.itemsize
    if n == 0:
        return None
    arr = np.frombuffer(raw[: n * RECORD.itemsize], dtype=RECORD)
    return arr[arr["volume"] > 0]


def hourly_rows(wanted: list[Target]) -> list[tuple[datetime, float, float, float, float, float]]:
    """(hour start UTC, open, high, low, close, volume) for every traded hour in the cached targets."""
    rows = []
    for t in wanted:
        rec = _records(t)
        if rec is None or len(rec) == 0:
            continue
        origin = datetime(t.start.year, t.start.month, t.start.day, tzinfo=timezone.utc)
        if t.kind == "month":
            for r in rec:
                rows.append((origin + timedelta(seconds=int(r["sec"])), r["open"], r["high"], r["low"], r["close"], float(r["volume"])))
        else:
            hours = rec["sec"] // 3600
            for h in np.unique(hours):
                g = rec[hours == h]
                rows.append((origin + timedelta(hours=int(h)), g["open"][0], g["high"].max(), g["low"].min(), g["close"][-1], float(g["volume"].sum())))
    rows.sort(key=lambda r: r[0])
    return [(ts, o / PRICE_SCALE, h / PRICE_SCALE, l / PRICE_SCALE, c / PRICE_SCALE, v) for ts, o, h, l, c, v in rows]


def candles(wanted: list[Target], timeframe: str) -> list[Candle]:
    """Hourly ("1h") or UTC-daily ("1d") silver candles from the cached targets."""
    rows = hourly_rows(wanted)
    if timeframe == "1h":
        return [Candle(asset=Asset.SILVER, timestamp=ts, open=o, high=h, low=l, close=c, volume=v, source=SOURCE) for ts, o, h, l, c, v in rows]
    if timeframe != "1d":
        raise ValueError(f"unsupported timeframe {timeframe}")
    out: list[Candle] = []
    day_rows: list = []

    def flush():
        if len(day_rows) >= MIN_DAILY_HOURS:
            d = day_rows[0][0]
            out.append(
                Candle(
                    asset=Asset.SILVER,
                    timestamp=datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
                    open=day_rows[0][1],
                    high=max(r[2] for r in day_rows),
                    low=min(r[3] for r in day_rows),
                    close=day_rows[-1][4],
                    volume=sum(r[5] for r in day_rows),
                    source=SOURCE,
                )
            )

    for row in rows:
        if day_rows and row[0].date() != day_rows[0][0].date():
            flush()
            day_rows = []
        day_rows.append(row)
    if day_rows:
        flush()
    return out


def coverage(wanted: list[Target]) -> dict:
    """How much of the wanted history is cached, for status screens."""
    today = date.today()
    # A recent file the feed hasn't published yet doesn't block completeness.
    done = sum(1 for t in wanted if t.cached() or not t.settled(today))
    return {"files_wanted": len(wanted), "files_cached": done, "complete": done == len(wanted)}
