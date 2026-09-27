"""Single place for tunable settings. Change behavior here, not by hunting
through modules.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"

# Assets this project tracks. Order doesn't matter.
TRACKED_ASSETS = ["BTC", "ETH", "SOL", "SILVER"]

# Timeframe for candles, e.g. "1d" (daily), "1h" (hourly).
TIMEFRAME = "1d"

# How often the 24/7 runner re-fetches data and recomputes features.
# Daily candles only produce new data once a day, so checking more often
# than this just re-reads the same numbers — this interval is meant to be
# "frequent enough not to miss a new day," not "as fast as possible."
RUNNER_INTERVAL_SECONDS = 3600  # 1 hour

# --- Price history -----------------------------------------------------------
# Earliest date kept per asset. Full histories are stitched from an older USD
# venue plus Binance, silver from Dukascopy spot (see data/history.py). BTC before 2013 is left out on
# purpose: volumes were tiny and single-venue prices were erratic.
HISTORY_START = {
    "BTC": "2013-01-01",
    "ETH": "2016-05-18",
    "SOL": "2020-08-11",
    "SILVER": "2003-05-05",  # Dukascopy spot XAG/USD; earlier years are too thin to use
}
# Stitching refuses to join two venues whose closes disagree by more than this
# (median absolute difference over their overlap).
STITCH_MAX_MEDIAN_DIFF = 0.03
STITCH_OVERLAP_DAYS = 90

# --- Ephemeris ---------------------------------------------------------------
EPHEMERIS_YEARS_OF_HISTORY = 60
EPHEMERIS_YEARS_AHEAD = 2  # so upcoming transits can be shown

# --- Transit playbook (analysis/) --------------------------------------------
# Forward horizons measured per speed class, in trading bars.
PLAYBOOK_HORIZONS = {
    "LUNAR": [1, 3, 5],
    "FAST": [1, 5, 10, 20],
    "SLOW": [20, 40, 60],
}
BIG_MOVE_PERCENTILE = 0.15  # top / bottom share of the asset's own N-day returns
SIDEWAYS_DISPLACEMENT_PERCENTILE = 0.25  # net move this small (ATR-normalised) ...
SIDEWAYS_MIN_RANGE_PERCENTILE = 0.25  # ... while the range stayed at least this normal
MIN_OCCURRENCES = 12  # below this a pattern is "insufficient_data", full stop
STRONG_MIN_OCCURRENCES = 25
FDR_STRONG = 0.05
FDR_MODERATE = 0.10
NOMINAL_ALPHA = 0.05
MIN_SHIFT_GAP_DAYS = 30  # circular shifts this close to the real calendar are skipped
UNIFORM_NULL_DRAWS = 2000
SIDEWAYS_HORIZONS = [10, 20]
INCLUDE_MOON = True
# Hourly drill-down from each transit's exact moment (analysis/timing.py).
TIMING_HORIZONS_HOURS = [6, 24, 72]
TIMING_ATR_HOURS = 24  # ATR window, in hourly bars, for the hourly outcome labels
TIMING_MIN_SHIFT_GAP_HOURS = 720  # circular shifts within 30 days of the real calendar are skipped
TIMING_MAX_WINDOW_DAYS = 20  # longest window the per-occurrence path looks at

# --- Scheduled analysis (runner) -----------------------------------------------
ANALYSIS_SCHEDULE_ENABLED = True
ANALYSIS_DAILY_AT_UTC = "00:30"  # after the 00:00 UTC daily close
PLACEBO_WEEKDAY = 6  # Sunday's scheduled run also runs the placebo check (0 = Monday)

# --- Strategy, backtest, journal ------------------------------------------------
# The strategy's own parameters live in strategy/rsi_divergence.py (fixed, not fitted).
BACKTEST_COST_PER_SIDE = {"BTC": 0.001, "ETH": 0.001, "SOL": 0.001, "SILVER": 0.0005}  # fees, as a fraction
BACKTEST_SLIPPAGE = 0.0005  # per side
SUGGESTION_EXPIRY_BARS = 3  # an undecided suggestion expires after this many daily bars
DRIFT_WATCH_Z = 1.0
DRIFT_SCALE_DOWN_Z = 2.0

# --- API server (python -m orbit.api) ----------------------------------------
API_HOST = os.getenv("ORBIT_API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("ORBIT_API_PORT", "8000"))
LIVE_CRYPTO_POLL_SECONDS = 3
LIVE_SILVER_POLL_SECONDS = 60  # Yahoo futures quotes are delayed anyway

# Secrets (never hardcode these — set them in a local .env file).
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
