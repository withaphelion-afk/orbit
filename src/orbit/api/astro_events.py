"""Turns raw ephemeris history into AstroEvent views: real sign-change
transits plus, where we have overlapping price history, the actual
historical average BTC move that followed past occurrences of that same
transit.

This is the astro-transit research track's first real output (see
README): "Jupiter entering Leo has happened N times before; BTC's average
5-day forward return after those was X%" — computed from real data, not
asserted. Crypto price history is short, so most transits (especially for
slow-moving planets) won't have any measurable overlap yet — that shows up
honestly as `btc_5d_mean_after: null`, matching the significance-testing
caution in the README's research notes rather than papering over it.
"""

from __future__ import annotations

from datetime import datetime

from orbit.api.schemas import AstroEvent
from orbit.config.settings import TIMEFRAME
from orbit.core.types import Asset, EphemerisSnapshot, Planet
from orbit.data.storage import load_candles, load_ephemeris_snapshots

FORWARD_DAYS = 5


def _sign_changes(snapshots: list[EphemerisSnapshot]) -> list[tuple[datetime, str, str]]:
    """(date, from_sign, to_sign) for every day the sign differs from the day before."""
    changes = []
    for prev, curr in zip(snapshots, snapshots[1:]):
        if curr.sign != prev.sign:
            changes.append((curr.date, prev.sign, curr.sign))
    return changes


def _btc_forward_return(btc_by_date: dict, sorted_dates: list, date_index: dict, event_date: datetime) -> float | None:
    idx = date_index.get(event_date)
    if idx is None or idx + FORWARD_DAYS >= len(sorted_dates):
        return None
    start = btc_by_date[sorted_dates[idx]].close
    end = btc_by_date[sorted_dates[idx + FORWARD_DAYS]].close
    return (end / start - 1) * 100


def build_astro_events(limit: int = 20) -> list[AstroEvent]:
    """Only the most recent `limit` changes per planet are ever candidates
    for the final top-`limit` list across all planets, so stats are only
    computed for those — avoids an O(n^2) scan for fast-moving bodies like
    the Moon (thousands of sign changes over 60 years).
    """
    btc_candles = load_candles(Asset.BTC, TIMEFRAME)
    btc_by_date = {c.timestamp: c for c in btc_candles}
    sorted_dates = sorted(btc_by_date)
    date_index = {d: i for i, d in enumerate(sorted_dates)}

    all_events = []
    for planet in Planet:
        snapshots = load_ephemeris_snapshots(planet)
        if not snapshots:
            continue
        snapshots.sort(key=lambda s: s.date)
        changes = _sign_changes(snapshots)
        recent_changes = changes[-limit:]
        recent_start_index = len(changes) - len(recent_changes)

        for offset, (date, from_sign, to_sign) in enumerate(recent_changes):
            i = recent_start_index + offset
            same_transition_before = [
                c for c in changes[:i] if c[2] == to_sign
            ]
            forward_returns = [
                r
                for r in (
                    _btc_forward_return(btc_by_date, sorted_dates, date_index, c[0])
                    for c in same_transition_before
                )
                if r is not None
            ]
            mean_after = sum(forward_returns) / len(forward_returns) if forward_returns else None

            all_events.append(
                AstroEvent(
                    id=f"{planet.value}-{to_sign}-{date.date().isoformat()}",
                    timestamp=date,
                    body=planet,
                    event=f"{planet.value.title()} enters {to_sign}",
                    prior_occurrences=len(same_transition_before),
                    btc_5d_mean_after=mean_after,
                )
            )

    all_events.sort(key=lambda e: e.timestamp, reverse=True)
    return all_events[:limit]
