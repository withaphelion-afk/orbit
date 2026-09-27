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

# Secrets (never hardcode these — set them in a local .env file).
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
