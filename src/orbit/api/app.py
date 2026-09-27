"""The Orbit web API. Serves the contract the React frontend expects
(web/src/api/types.ts) from whatever data the runner has already fetched
and computed — this process doesn't fetch or compute anything itself.

Run it with:
    uv run uvicorn orbit.api.app:app --reload

The frontend's Vite dev server proxies /api and /ws here by default
(http://127.0.0.1:8000) — see web/vite.config.ts.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from orbit.api.astro_events import build_astro_events
from orbit.api.live_prices import fetch_current_price
from orbit.api.quotes import build_quotes, build_signals
from orbit.api.schemas import (
    AstroEvent,
    DecisionRequest,
    DriftReport,
    JournalRow,
    Quote,
    Signal,
    SystemStatus,
)
from orbit.api.system_status import build_system_status
from orbit.config.settings import TIMEFRAME, TRACKED_ASSETS
from orbit.core.types import Asset, Candle
from orbit.data.storage import load_candles

app = FastAPI(title="Orbit API")

# Dev-only: the Vite dev server proxies through this same origin, but CORS
# is left open here to keep local frontend/backend iteration friction-free.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TICK_INTERVAL_SECONDS = 5
ASSETS = [Asset(name) for name in TRACKED_ASSETS]


@app.get("/api/quotes", response_model=list[Quote])
def get_quotes() -> list[Quote]:
    return build_quotes(ASSETS)


@app.get("/api/candles/{asset}", response_model=list[Candle])
def get_candles(asset: Asset) -> list[Candle]:
    return load_candles(asset, TIMEFRAME)


@app.get("/api/signals/{asset}", response_model=list[Signal])
def get_signals(asset: Asset) -> list[Signal]:
    return build_signals(asset)


@app.get("/api/suggestions")
def get_suggestions() -> list:
    # No strategy layer yet — honestly empty rather than fabricated.
    return []


@app.post("/api/suggestions/{suggestion_id}/decision", response_model=JournalRow)
def post_decision(suggestion_id: str, request: DecisionRequest) -> JournalRow:
    # There are no live suggestions to act on yet (see get_suggestions).
    raise HTTPException(status_code=404, detail="No such suggestion — the strategy layer isn't built yet.")


@app.get("/api/journal")
def get_journal() -> list:
    return []


@app.get("/api/drift", response_model=DriftReport)
def get_drift() -> DriftReport:
    # No backtest or live trading history exists yet — a neutral, honest
    # zero-state rather than invented numbers.
    return DriftReport(
        status="OK",
        z_score=0.0,
        scale_down_at=2.0,
        expected_win_rate=0.0,
        live_win_rate=0.0,
        expected_avg_r=0.0,
        live_avg_r=0.0,
        expected_max_dd=0.0,
        live_max_dd=0.0,
        backtest_trades=0,
        live_trades=0,
        curve=[],
    )


@app.get("/api/astro", response_model=list[AstroEvent])
def get_astro() -> list[AstroEvent]:
    return build_astro_events()


@app.get("/api/system", response_model=SystemStatus)
def get_system() -> SystemStatus:
    return build_system_status()


@app.websocket("/ws")
async def websocket_ticks(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            for asset in ASSETS:
                price = await asyncio.to_thread(fetch_current_price, asset)
                if price is not None:
                    await websocket.send_json(
                        {
                            "type": "tick",
                            "asset": asset.value,
                            "price": price,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
            await asyncio.sleep(TICK_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        pass
