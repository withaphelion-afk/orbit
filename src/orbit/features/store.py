"""The feature store: save/load computed FeatureRecords, one CSV per asset.

This is the boundary described in the project's signal research notes
(see README): raw data lives in data/, features get computed once here,
and strategy/ will only ever read from this store — never straight from
candles or ephemeris. That keeps every consumer (the scorecard today, an
ML model later) working from identical inputs.

Stored in "long" format (one row per asset/feature/date) rather than one
column per feature, since new features get added constantly here and a
long format never needs a schema change for that.
"""

from __future__ import annotations

import csv
from pathlib import Path

from orbit.config.settings import DATA_DIR
from orbit.core.types import Asset, FeatureRecord

FEATURES_DIR = DATA_DIR / "features"


def _csv_path(asset: Asset) -> Path:
    return FEATURES_DIR / f"{asset.value}.csv"


def save_features(records: list[FeatureRecord]) -> Path:
    """Append feature records to the given asset's store.

    Appends rather than overwrites (unlike candle/ephemeris storage),
    since features get computed incrementally over time as new data and
    new feature types arrive — recomputing everything from scratch every
    time would throw away that history.
    """
    if not records:
        raise ValueError("no feature records to save")

    asset = records[0].asset
    path = _csv_path(asset)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new_file = not path.exists()

    with path.open("a", newline="") as f:
        writer = csv.writer(f)
        if is_new_file:
            writer.writerow(["date", "name", "value"])
        for record in records:
            writer.writerow([record.date.isoformat(), record.name, record.value])
    return path


def load_features(asset: Asset, name: str | None = None) -> list[FeatureRecord]:
    """Read feature records back for an asset, optionally filtered to one feature name."""
    path = _csv_path(asset)
    if not path.exists():
        return []

    records = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            if name is not None and row["name"] != name:
                continue
            records.append(
                FeatureRecord(
                    asset=asset,
                    name=row["name"],
                    date=row["date"],
                    value=float(row["value"]),
                )
            )
    return records
