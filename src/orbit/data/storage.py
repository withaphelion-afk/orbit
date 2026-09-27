"""Save and load candles as CSV files under the local data/ cache.

CSV is intentionally simple for now — one file per asset+timeframe. If this
ever becomes a bottleneck (many assets, high-frequency data), swap this for
a real time-series database without touching any other module, since
everything else only talks to Candle objects.
"""

from __future__ import annotations

import csv
from pathlib import Path

from orbit.config.settings import DATA_DIR
from orbit.core.types import Asset, Candle, EphemerisSnapshot, Planet


def _csv_path(asset: Asset, timeframe: str) -> Path:
    return DATA_DIR / f"{asset.value}_{timeframe}.csv"


def save_candles(candles: list[Candle], timeframe: str) -> Path:
    """Write candles to CSV, overwriting any existing file for that asset+timeframe.

    Assumes all candles passed in are for the same asset.
    """
    if not candles:
        raise ValueError("no candles to save")

    asset = candles[0].asset
    path = _csv_path(asset, timeframe)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for candle in candles:
            writer.writerow(
                [
                    candle.timestamp.isoformat(),
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                ]
            )
    return path


def load_candles(asset: Asset, timeframe: str) -> list[Candle]:
    """Read candles back from CSV. Returns an empty list if no file exists yet."""
    path = _csv_path(asset, timeframe)
    if not path.exists():
        return []

    candles = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            candles.append(
                Candle(
                    asset=asset,
                    timestamp=row["timestamp"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
    return candles


def _ephemeris_csv_path(planet: Planet) -> Path:
    return DATA_DIR / "ephemeris" / f"{planet.value}.csv"


def save_ephemeris_snapshots(snapshots: list[EphemerisSnapshot]) -> Path:
    """Write ephemeris snapshots to CSV, overwriting any existing file for that planet.

    Assumes all snapshots passed in are for the same planet.
    """
    if not snapshots:
        raise ValueError("no snapshots to save")

    planet = snapshots[0].planet
    path = _ephemeris_csv_path(planet)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "longitude", "sign", "retrograde"])
        for snap in snapshots:
            writer.writerow([snap.date.isoformat(), snap.longitude, snap.sign, snap.retrograde])
    return path


def load_ephemeris_snapshots(planet: Planet) -> list[EphemerisSnapshot]:
    """Read ephemeris snapshots back from CSV. Empty list if no file exists yet."""
    path = _ephemeris_csv_path(planet)
    if not path.exists():
        return []

    snapshots = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            snapshots.append(
                EphemerisSnapshot(
                    planet=planet,
                    date=row["date"],
                    longitude=float(row["longitude"]),
                    sign=row["sign"],
                    retrograde=row["retrograde"] == "True",
                )
            )
    return snapshots
