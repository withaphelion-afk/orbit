"""Read-only access to everything the scripts and runner have stored, cached
until the underlying file changes.

The API never fetches history or computes research itself; that's the
runner's and the playbook job's work. It only reads their output, so a slow
request can never hold up (or be held up by) the heavy jobs.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

from orbit.config.settings import DATA_DIR, TIMEFRAME
from orbit.core.types import Asset, AssetPlaybook, Candle, TransitEvent
from orbit.data.dates import today_utc
from orbit.data.history import REPORT_PATH
from orbit.data.storage import _csv_path, load_candles
from orbit.features.regime import VALUE_TO_REGIME, regime_gate_by_day, trend_values
from orbit.analysis.playbook import ANALYSIS_DIR
from orbit.vedic.events import EVENTS_CACHE as VEDIC_EVENTS
from orbit.vedic.events import load_events as load_vedic_events

LOG_PATH = DATA_DIR / "logs" / "runner.log"
_LOG_LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ \[(\w+)\] (.*)$")

_cache: dict[str, tuple[float, Any]] = {}


def _mtime(paths: list[Path]) -> float:
    return max((p.stat().st_mtime for p in paths if p.exists()), default=0.0)


def _cached(key: str, paths: list[Path], build: Callable[[], Any]) -> Any:
    stamp = _mtime(paths)
    hit = _cache.get(key)
    if hit and hit[0] == stamp:
        return hit[1]
    value = build()
    _cache[key] = (stamp, value)
    return value


def candles(asset: Asset, timeframe: str = TIMEFRAME) -> list[Candle]:
    return _cached(f"candles:{asset.value}:{timeframe}", [_csv_path(asset, timeframe)], lambda: load_candles(asset, timeframe))


def completed(asset: Asset) -> list[Candle]:
    """Stored bars excluding today's still-forming one."""
    today = today_utc()
    return [c for c in candles(asset) if c.timestamp < today]


def price_series(asset: Asset):
    """Completed daily bars as arrays (analysis/series.py), for the strategy's signals."""
    from orbit.analysis.series import load_price_series

    return _cached(f"series:{asset.value}:{today_utc().date()}", [_csv_path(asset, TIMEFRAME)], lambda: load_price_series(asset))


def backtest_exists() -> bool:
    from orbit.backtest.engine import BACKTEST_DIR

    return (BACKTEST_DIR / "summary.json").exists()


def regime_by_day(asset: Asset) -> tuple[dict[datetime, str], str]:
    """{day: BULL/BEAR/CHOPPY} and its scope. Crypto reads the shared BTC/ETH gate;
    silver has no gate, so it reads its own trend under the same rule."""
    if asset == Asset.SILVER:
        def build():
            bars = completed(Asset.SILVER)
            values = trend_values([c.close for c in bars])
            return {c.timestamp: VALUE_TO_REGIME[v].value for c, v in zip(bars, values) if not np.isnan(v)}

        return _cached("trend:SILVER", [_csv_path(Asset.SILVER, TIMEFRAME)], build), "OWN"

    def build_gate():
        gate = regime_gate_by_day(completed(Asset.BTC), completed(Asset.ETH))
        return {d: VALUE_TO_REGIME[v].value for d, v in sorted(gate.items())}

    return _cached("gate", [_csv_path(Asset.BTC, TIMEFRAME), _csv_path(Asset.ETH, TIMEFRAME)], build_gate), "SHARED"


def history_report() -> dict:
    return _cached("report", [REPORT_PATH], lambda: json.loads(REPORT_PATH.read_text(encoding="utf-8")) if REPORT_PATH.exists() else {})


EVENTS_PATH = ANALYSIS_DIR / "events.json"


def transit_events() -> list[TransitEvent]:
    """Vedic events with exact moments, as saved by the last analysis run, or
    straight from the Vedic detector if no run has happened yet (or the last
    run predates the switch to Vedic rules: its events have no labels)."""
    if EVENTS_PATH.exists():
        saved = _cached(
            "events",
            [EVENTS_PATH],
            lambda: [TransitEvent.model_validate(e) for e in json.loads(EVENTS_PATH.read_text(encoding="utf-8"))],
        )
        if saved and all(e.label for e in saved[:50]):
            return saved
    return _cached("events-vedic", [VEDIC_EVENTS], load_vedic_events)


def playbook(asset: Asset) -> AssetPlaybook | None:
    path = ANALYSIS_DIR / f"{asset.value}.json"
    return _cached(
        f"playbook:{asset.value}",
        [path],
        lambda: AssetPlaybook.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None,
    )


def playbook_meta() -> dict | None:
    path = ANALYSIS_DIR / "meta.json"
    return _cached("meta", [path], lambda: json.loads(path.read_text(encoding="utf-8")) if path.exists() else None)


def placebo() -> dict | None:
    path = ANALYSIS_DIR / "placebo.json"

    def build():
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if k != "runs"}

    return _cached("placebo", [path], build)


def runner_log(limit: int = 40) -> list[tuple[datetime, str, str]]:
    """The last `limit` log lines, newest first (tracebacks and blank lines skipped)."""
    if not LOG_PATH.exists():
        return []
    with LOG_PATH.open(encoding="utf-8", errors="replace") as f:
        tail = f.readlines()[-400:]
    out = []
    for line in reversed(tail):
        m = _LOG_LINE.match(line.rstrip())
        if m:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").astimezone(timezone.utc)
            out.append((ts, m.group(2), m.group(3)))
            if len(out) >= limit:
                break
    return out
