"""One definition of "a daily bar's date": midnight UTC of the calendar day
the bar belongs to.

Venues stamp daily bars differently (Binance at 00:00 UTC, Yahoo at the
exchange's local midnight, which is 04:00 or 05:00 UTC for New York). Joining
prices, features and ephemeris by date only works if they all agree, so every
fetcher normalises through here.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def utc_day(d: datetime | date | str) -> datetime:
    """Midnight UTC of the given day. Naive datetimes are treated as UTC."""
    if isinstance(d, str):
        d = datetime.fromisoformat(d)
    if isinstance(d, datetime):
        if d.tzinfo is not None:
            d = d.astimezone(timezone.utc)
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def from_unix(seconds: float, utc_offset_seconds: int = 0) -> datetime:
    """A bar timestamp in unix seconds -> its calendar day, in the venue's own
    timezone (`utc_offset_seconds`, e.g. -14400 for New York in summer)."""
    local = datetime.fromtimestamp(seconds + utc_offset_seconds, tz=timezone.utc)
    return utc_day(local)


def from_unix_exact(seconds: float) -> datetime:
    """A unix timestamp as an exact UTC datetime (for intraday bars)."""
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def bar_time(seconds: float, timeframe: str, utc_offset_seconds: int = 0) -> datetime:
    """A bar's timestamp: its calendar day for daily bars, the exact hour otherwise."""
    return from_unix(seconds, utc_offset_seconds) if timeframe == "1d" else from_unix_exact(seconds)


def today_utc() -> datetime:
    return utc_day(datetime.now(timezone.utc))


def days_between(start: datetime, end: datetime) -> int:
    return (utc_day(end) - utc_day(start)) // timedelta(days=1)
