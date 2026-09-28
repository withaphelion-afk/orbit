"""Vedic astro features for the feature store, one set per day of an asset's history.

Astrology isn't specific to one asset, but the feature store is asset-keyed
(each strategy reads only its own asset's file), so the same Vedic features
are written once per tracked asset, for the days that asset has bars.

Per graha (sidereal, Vedic rules; see orbit/vedic):
    {graha}_rashi      rashi index 0 (Mesha) .. 11 (Meena), read at 00:00 UTC
    {graha}_vakri      1 while retrograde (Mars..Saturn)
    {graha}_asta       1 while combust (Mars..Saturn)
plus moon_nakshatra (0 Ashwini .. 26 Revati).
Values are floats so every feature can be scored and combined the same way.
"""

from __future__ import annotations

import numpy as np

from orbit.core.types import Asset, Candle, FeatureRecord, Planet
from orbit.vedic import zodiac as z
from orbit.vedic.sky import Sky, load_sky
from orbit.vedic.states import SAMPLES_PER_DAY, build_states


def vedic_features(candles: list[Candle], sky: Sky | None = None) -> list[FeatureRecord]:
    if not candles:
        return []
    sky = sky or load_sky()
    states = build_states(sky)
    asset: Asset = candles[0].asset
    day0 = states.days[0]
    records = []
    series = {}
    for g in z.GRAHAS:
        if g == Planet.KETU:
            continue
        series[f"{g.value.lower()}_rashi"] = (sky.lon[g][::SAMPLES_PER_DAY] // 30).astype(float)
    for g in z.STATION_GRAHAS:
        series[f"{g.value.lower()}_vakri"] = states.masks[f"{g.value}:VAKRI"][1].astype(float)
        series[f"{g.value.lower()}_asta"] = states.masks[f"{g.value}:ASTA"][1].astype(float)
    series["moon_nakshatra"] = (sky.lon[Planet.MOON][::SAMPLES_PER_DAY] // z.NAKSHATRA_SPAN).astype(float)
    for c in candles:
        i = int((np.datetime64(c.timestamp.replace(tzinfo=None), "D") - day0).astype(int))
        if not 0 <= i < len(states.days):
            continue
        for name, values in series.items():
            records.append(FeatureRecord(asset=asset, name=name, date=c.timestamp, value=float(values[i])))
    return records
