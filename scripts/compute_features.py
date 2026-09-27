"""Manual script: compute every feature type from already-fetched raw data
and write them into the feature store.

Run scripts/fetch_data.py and scripts/fetch_ephemeris.py first. Then:
    uv run python scripts/compute_features.py
"""

from __future__ import annotations

import shutil

from orbit.core.types import Asset, Planet
from orbit.data.storage import load_candles, load_ephemeris_snapshots
from orbit.features.astro import ephemeris_to_features
from orbit.features.regime import compute_regime_series
from orbit.features.store import FEATURES_DIR, save_features
from orbit.features.technical import compute_technical_features

TIMEFRAME = "1d"
CRYPTO_ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL]
ALL_ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL, Asset.SILVER]

if __name__ == "__main__":
    # This script recomputes the entire feature history every run, but
    # save_features() appends — clear the store first so re-running
    # doesn't duplicate every row.
    shutil.rmtree(FEATURES_DIR, ignore_errors=True)

    # Technical features: independent per asset.
    for asset in ALL_ASSETS:
        candles = load_candles(asset, TIMEFRAME)
        if not candles:
            print(f"{asset.value}: no candles found, skipping technical features")
            continue
        records = compute_technical_features(candles)
        if records:
            save_features(records)
            print(f"{asset.value}: saved {len(records)} technical feature rows")

    # Regime gate: one shared BTC/ETH-derived reading, logged under each
    # crypto asset (not silver — no crypto correlation logic applies there).
    btc_candles = load_candles(Asset.BTC, TIMEFRAME)
    eth_candles = load_candles(Asset.ETH, TIMEFRAME)
    if btc_candles and eth_candles:
        for asset in CRYPTO_ASSETS:
            records = compute_regime_series(btc_candles, eth_candles, target_asset=asset)
            if records:
                save_features(records)
                print(f"{asset.value}: saved {len(records)} regime feature rows")

    # Astro features: same planetary data, written once per tracked asset.
    for planet in Planet:
        snapshots = load_ephemeris_snapshots(planet)
        if not snapshots:
            continue
        for asset in ALL_ASSETS:
            records = ephemeris_to_features(snapshots, asset)
            save_features(records)
        print(f"{planet.value}: saved {len(snapshots)} days x {len(ALL_ASSETS)} assets")
