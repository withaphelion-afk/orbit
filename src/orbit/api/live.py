"""Live prices for the terminal: Binance for crypto, Yahoo (delayed) for silver.

One background task polls both on their own intervals and pushes each new
price to every connected WebSocket. The UI never talks to a venue directly,
so there is exactly one place prices come from.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import WebSocket

from orbit.config.settings import LIVE_CRYPTO_POLL_SECONDS, LIVE_SILVER_POLL_SECONDS
from orbit.core.types import Asset
from orbit.data import silver
from orbit.data.binance import SYMBOLS
from orbit.data.http import get_json

log = logging.getLogger("orbit.api.live")
TICKER_URL = "https://api.binance.com/api/v3/ticker/price"


@dataclass
class Tick:
    asset: Asset
    price: float
    at: datetime
    source: str  # "LIVE" or "DELAYED"

    def message(self) -> str:
        return json.dumps(
            {"type": "tick", "asset": self.asset.value, "price": self.price, "timestamp": self.at.isoformat(), "source": self.source}
        )


class LiveFeed:
    def __init__(self) -> None:
        self.latest: dict[Asset, Tick] = {}
        self.clients: set[WebSocket] = set()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        silver_due = 0.0
        loop = asyncio.get_running_loop()
        while True:
            try:
                await self._poll_crypto()
            except Exception as exc:  # a dropped poll must never kill the feed
                log.warning("crypto poll failed: %s", exc)
            if loop.time() >= silver_due:
                silver_due = loop.time() + LIVE_SILVER_POLL_SECONDS
                try:
                    price = await asyncio.to_thread(silver.fetch_latest_price)
                    if price:
                        await self._publish(Tick(Asset.SILVER, float(price), datetime.now(timezone.utc), "DELAYED"))
                except Exception as exc:
                    log.warning("silver poll failed: %s", exc)
            await asyncio.sleep(LIVE_CRYPTO_POLL_SECONDS)

    async def _poll_crypto(self) -> None:
        symbols = json.dumps(list(SYMBOLS.values()), separators=(",", ":"))
        rows = await asyncio.to_thread(get_json, TICKER_URL, {"symbols": symbols}, 10)
        by_symbol = {row["symbol"]: float(row["price"]) for row in rows}
        now = datetime.now(timezone.utc)
        for asset, symbol in SYMBOLS.items():
            if symbol in by_symbol:
                await self._publish(Tick(asset, by_symbol[symbol], now, "LIVE"))

    async def _publish(self, tick: Tick) -> None:
        prev = self.latest.get(tick.asset)
        self.latest[tick.asset] = tick
        if prev and prev.price == tick.price:
            return  # nothing moved; don't spam clients
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(tick.message())
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def serve(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)
        try:
            for tick in self.latest.values():  # current prices straight away
                await ws.send_text(tick.message())
            while True:
                await ws.receive_text()  # we don't expect messages; this waits for disconnect
        except Exception:
            pass
        finally:
            self.clients.discard(ws)
