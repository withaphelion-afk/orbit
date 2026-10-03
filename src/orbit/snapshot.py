"""Render every API answer to static JSON files, for a web terminal with no server.

    python -m orbit.snapshot site

The free cloud setup has no always-on server: GitHub Actions jobs compute
everything, then call this to write each GET endpoint's answer to a file and
push the files to the data repo's `site` branch (orbit.outputs --site). The web
terminal (built with VITE_ORBIT_STATIC=1, hosted on Vercel) reads them from
there with the viewer's GitHub token.

The answers come from the real API (create_app, through a test client), so the
static terminal shows exactly what the server would. Layout, mirrored by
web/src/api/static.ts:

    quotes.json, regime.json, sky.json, system.json, suggestions.json, journal.json,
    drift.json, backtest.json, calibration.json, playbook.json, snapshot.json
    transits.json            the default window (90 days back to 180 ahead)
    transits-all.json        every event except the Moon's, for the chart's full history
    candles/{ASSET}.json, signals/{ASSET}.json, playbook/{ASSET}.json, model/{ASSET}.json
    patterns/{ASSET}/{hex of the pattern id}.json
    hourly/{ASSET}/{YEAR}.json   hourly bars as [time, open, high, low, close, volume] rows
    analysis/runs.json, analysis/current.json, analysis/schedule.json

An endpoint that answers with an error (a report not generated yet, say) is
written as {"__error": {"status": ..., "detail": ...}}, so the terminal shows
the same explanation the server would.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

from orbit.core.types import Asset

ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL, Asset.SILVER]


def pattern_key(pattern_id: str) -> str:
    """A file-name-safe, reversible key for a pattern id (ids contain ':' and '|')."""
    return pattern_id.encode("utf-8").hex()


def _client():
    warnings.filterwarnings("ignore", message=".*httpx.*")
    from fastapi.testclient import TestClient

    from orbit.api.app import create_app

    return TestClient(create_app(live=False))


def _write(out: Path, rel: str, body: str) -> None:
    path = out / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _render(client, out: Path, rel: str, url: str) -> object | None:
    """Write one endpoint's answer to out/rel; returns the parsed body when it succeeded."""
    response = client.get(url)
    if response.status_code == 200:
        _write(out, rel, response.text)
        return response.json()
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    _write(out, rel, json.dumps({"__error": {"status": response.status_code, "detail": str(detail)}}))
    return None


def build(out: Path) -> int:
    """Write the full snapshot into `out` (replacing it). Returns the number of files."""
    from orbit.api import store

    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    client = _client()

    for rel, url in (
        ("quotes.json", "/api/quotes"),
        ("regime.json", "/api/regime"),
        ("sky.json", "/api/sky"),
        ("system.json", "/api/system"),
        ("suggestions.json", "/api/suggestions"),
        ("journal.json", "/api/journal"),
        ("drift.json", "/api/drift"),
        ("backtest.json", "/api/backtest"),
        ("calibration.json", "/api/calibration"),
        ("playbook.json", "/api/playbook"),
        ("transits.json", "/api/transits"),
        ("transits-all.json", "/api/transits?from=1990-01-01&to=2100-01-01"),
        ("analysis/runs.json", "/api/analysis/runs?limit=40"),
        ("analysis/current.json", "/api/analysis/runs/current"),
        ("analysis/schedule.json", "/api/analysis/schedule"),
    ):
        _render(client, out, rel, url)

    for asset in ASSETS:
        a = asset.value
        _render(client, out, f"candles/{a}.json", f"/api/candles/{a}")
        _render(client, out, f"signals/{a}.json", f"/api/signals/{a}")
        _render(client, out, f"model/{a}.json", f"/api/model/{a}")
        playbook = store.playbook(asset)
        if _render(client, out, f"playbook/{a}.json", f"/api/playbook/{a}") and playbook:
            for result in playbook.patterns:
                _write(out, f"patterns/{a}/{pattern_key(result.pattern_id)}.json", result.model_dump_json())
        # Compact rows [time, open, high, low, close, volume]: the drill-down only reads these,
        # and spelling out every field would make the hourly history ~3x larger.
        by_year: dict[int, list[list]] = {}
        for bar in store.candles(asset, "1h"):
            by_year.setdefault(bar.timestamp.year, []).append(
                [bar.timestamp.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume]
            )
        for year, rows in by_year.items():
            _write(out, f"hourly/{a}/{year}.json", json.dumps(rows, separators=(",", ":")))

    files = sum(1 for p in out.rglob("*") if p.is_file())
    _write(out, "snapshot.json", json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "files": files + 1}))
    return files + 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the API's answers to static files")
    parser.add_argument("out", type=Path, help="folder to write (it is replaced)")
    args = parser.parse_args()
    print(f"Snapshot: {build(args.out)} files in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
