"""Price bars for the divergence system at 1H, 4H, 1D and 1W, as numpy arrays.

1H and 1D come from the stored histories (data/{ASSET}_1h.csv, _1d.csv); 4H is
built from 1H (UTC 00/04/08/12/16/20 buckets) and 1W from 1D (weeks starting
Monday, UTC). Only completed bars are returned: the bar still forming is
dropped, so nothing here ever sees a price that wasn't final.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from orbit.config.settings import DATA_DIR
from orbit.core.types import Asset

TIMEFRAMES = ("1h", "4h", "1d", "1w")
SECONDS = {"1h": 3600, "4h": 4 * 3600, "1d": 86400, "1w": 7 * 86400}
WEEK_ORIGIN = 4 * 86400  # 1970-01-05 was a Monday: weeks are counted from there


@dataclass
class Bars:
    asset: Asset
    timeframe: str
    time: np.ndarray  # int64 epoch seconds of each bar's open
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray

    def __len__(self) -> int:
        return len(self.time)

    def tail(self, n: int) -> "Bars":
        s = slice(max(0, len(self) - n), None)
        return Bars(self.asset, self.timeframe, self.time[s], self.open[s], self.high[s], self.low[s], self.close[s], self.volume[s])


def _read(asset: Asset, base: str) -> Bars:
    path = DATA_DIR / f"{asset.value}_{base}.csv"
    rows = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                ts = datetime.fromisoformat(r["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                rows.append((int(ts.timestamp()), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r["volume"] or 0)))
    a = np.array(rows, dtype=float).reshape(-1, 6)
    return Bars(asset, base, a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5])


def aggregate(b: Bars, timeframe: str) -> Bars:
    """Group bars into longer ones (4H from 1H, 1W from 1D); a bucket is kept only if its last sub-bar has closed."""
    size = SECONDS[timeframe]
    origin = WEEK_ORIGIN if timeframe == "1w" else 0
    if not len(b):
        return Bars(b.asset, timeframe, b.time, b.open, b.high, b.low, b.close, b.volume)
    bucket = (b.time - origin) // size
    starts = np.flatnonzero(np.r_[True, bucket[1:] != bucket[:-1]])
    ends = np.r_[starts[1:], len(b)] - 1
    t = bucket[starts] * size + origin
    return Bars(
        b.asset,
        timeframe,
        t.astype(np.int64),
        b.open[starts],
        np.maximum.reduceat(b.high, starts),
        np.minimum.reduceat(b.low, starts),
        b.close[ends],
        np.add.reduceat(b.volume, starts),
    )


def completed(b: Bars, now: float | None = None) -> Bars:
    """Drop the bar that hasn't closed yet."""
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    keep = b.time + SECONDS[b.timeframe] <= now
    return Bars(b.asset, b.timeframe, b.time[keep], b.open[keep], b.high[keep], b.low[keep], b.close[keep], b.volume[keep])


def load(asset: Asset, timeframe: str, now: float | None = None) -> Bars:
    if timeframe in ("1h", "1d"):
        return completed(_read(asset, timeframe), now)
    base = "1h" if timeframe == "4h" else "1d"
    return completed(aggregate(_read(asset, base), timeframe), now)
