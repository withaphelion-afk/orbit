"""Reusable feature-computation step, shared by scripts/compute_features.py
and the 24/7 runner.
"""

from __future__ import annotations

import shutil

from orbit.config.settings import TIMEFRAME
from orbit.core.types import Asset, Planet
from orbit.data.storage import load_candles, load_ephemeris_snapshots
from orbit.features.astro import ephemeris_to_features
from orbit.features.regime import compute_regime_series
from orbit.features.store import FEATURES_DIR, save_features
from orbit.features.technical import compute_technical_features

CRYPTO_ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL]
ALL_ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL, Asset.SILVER]


def compute_all_features() -> None:
    """Recompute every feature type from whatever raw data is currently
    stored, and rewrite the feature store from scratch.

    Full recompute rather than incremental — simpler to reason about, and
    cheap enough at this data volume (see compute_features.py timing).
    """
    shutil.rmtree(FEATURES_DIR, ignore_errors=True)

    for asset in ALL_ASSETS:
        candles = load_candles(asset, TIMEFRAME)
        if not candles:
            continue
        records = compute_technical_features(candles)
        if records:
            save_features(records)

    btc_candles = load_candles(Asset.BTC, TIMEFRAME)
    eth_candles = load_candles(Asset.ETH, TIMEFRAME)
    if btc_candles and eth_candles:
        for asset in CRYPTO_ASSETS:
            records = compute_regime_series(btc_candles, eth_candles, target_asset=asset)
            if records:
                save_features(records)

    for planet in Planet:
        snapshots = load_ephemeris_snapshots(planet)
        if not snapshots:
            continue
        for asset in ALL_ASSETS:
            save_features(ephemeris_to_features(snapshots, asset))
