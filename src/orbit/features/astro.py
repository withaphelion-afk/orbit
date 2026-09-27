"""Turn ephemeris snapshots into numeric FeatureRecords.

Astrology's transits aren't specific to one tradeable asset — a Jupiter
sign change is the same fact whether you trade BTC or silver. We still
tag each record with an asset, though, because the feature store is
asset-keyed and the per-asset entry layer only reads its own asset's
file — so the same ephemeris feature gets written once per tracked asset.

`sign_index` (0-11, Aries=0 ... Pisces=11) is used instead of storing the
sign name as text, since FeatureRecord.value is always a float — this
keeps every feature combinable/scorable the same way.
"""

from __future__ import annotations

from orbit.core.types import Asset, EphemerisSnapshot, FeatureRecord
from orbit.data.ephemeris import ZODIAC_SIGNS


def ephemeris_to_features(snapshots: list[EphemerisSnapshot], asset: Asset) -> list[FeatureRecord]:
    records = []
    for snap in snapshots:
        planet_name = snap.planet.value.lower()
        sign_index = float(ZODIAC_SIGNS.index(snap.sign))
        records.append(
            FeatureRecord(asset=asset, name=f"{planet_name}_sign_index", date=snap.date, value=sign_index)
        )
        records.append(
            FeatureRecord(
                asset=asset,
                name=f"{planet_name}_retrograde",
                date=snap.date,
                value=1.0 if snap.retrograde else 0.0,
            )
        )
    return records
