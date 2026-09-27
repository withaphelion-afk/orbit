"""Manual script: build or update the stored price history for BTC/ETH/SOL/silver.

The first run fetches full stitched histories (BTC from 2013, ETH from 2016,
SOL from 2020, silver from 2000; see data/history.py). Later runs only fetch
the last few days.

Run it with:
    uv run python scripts/fetch_data.py
"""

from orbit.data.pipeline import fetch_all_prices

if __name__ == "__main__":
    for asset, report in fetch_all_prices().items():
        if report is None:
            print(f"{asset}: updated incrementally")
            continue
        overlap = report["median_abs_diff"]
        joined = f", stitched with a median {overlap:.2%} gap over {report['overlap_days']} days" if overlap is not None else ""
        sources = " + ".join(f"{s['source']} ({s['bars']})" for s in report["sources"])
        print(f"{asset}: {report['bars']} bars {report['first'][:10]} -> {report['last'][:10]} from {sources}{joined}")
