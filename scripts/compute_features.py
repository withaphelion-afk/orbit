"""Manual script: compute every feature type from already-fetched raw data
and write them into the feature store.

Run scripts/fetch_data.py and scripts/fetch_ephemeris.py first. Then:
    uv run python scripts/compute_features.py
"""

from orbit.features.pipeline import compute_all_features

if __name__ == "__main__":
    compute_all_features()
    print("Recomputed the feature store from currently stored raw data.")
