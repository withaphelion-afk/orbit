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

# Secrets (never hardcode these — set them in a local .env file).
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
