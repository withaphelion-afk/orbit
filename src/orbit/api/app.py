"""The HTTP + WebSocket API the web terminal reads. Run with:

    uv run python -m orbit.api

Read-only over stored data (see store.py) plus a live price feed (live.py).
Endpoints for layers that don't exist yet (strategy, journal, backtest)
answer honestly: empty lists, 501 for writes, 404 for reports, and
/api/system says which components are built so the UI can show why.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import numpy as np
from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.gzip import GZipMiddleware

from orbit.config import settings
from orbit.core.types import Asset, Candle, ConfidenceLabel, Direction, PatternResult, Signal
from orbit.data.dates import today_utc, utc_day
from orbit.api import store
from orbit.api.live import LiveFeed
from orbit.api.schemas import (
    Components,
    FeedStatus,
    LogLine,
    NotableFor,
    PatternSummary,
    PlaybookOverview,
    PlaybookView,
    Quote,
    RegimeReading,
    RunnerStatus,
    SkyPosition,
    SystemStatus,
    TransitView,
)
from orbit.analysis.confidence import RANK
from orbit.analysis.patterns import patterns_for_event
from orbit.analysis.transit_events import event_label
from orbit.runner.status import read_status

ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL, Asset.SILVER]
LIVE_FRESH = timedelta(minutes=5)
NOT_BUILT = "The strategy and journal layers aren't built yet, so there is nothing to decide on or log."


def create_app(live: bool = True) -> FastAPI:
    feed = LiveFeed()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if live:
            feed.start()
        yield
        await feed.stop()

    app = FastAPI(title="Orbit API", lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.state.feed = feed

    # ------------------------------------------------------------ prices

    def live_tick(asset: Asset):
        tick = feed.latest.get(asset)
        if tick and datetime.now(timezone.utc) - tick.at < LIVE_FRESH:
            return tick
        return None

    @app.get("/api/quotes", response_model=list[Quote])
    def quotes():
        out = []
        today = today_utc()
        for asset in ASSETS:
            bars = store.candles(asset)
            if not bars:
                continue
            done = [c for c in bars if c.timestamp < today]
            forming = bars[-1] if bars[-1].timestamp >= today else None
            prev = done[-1].close if done else bars[-1].close
            tick = live_tick(asset)
            last = tick.price if tick else (forming.close if forming else prev)
            highs = [x for x in (forming.high if forming else None, last) if x is not None]
            lows = [x for x in (forming.low if forming else None, last) if x is not None]
            regimes, scope = store.regime_by_day(asset)
            latest_regime = regimes[max(regimes)] if regimes else None
            out.append(
                Quote(
                    asset=asset,
                    last=last,
                    prev_close=prev,
                    day_high=max(highs),
                    day_low=min(lows),
                    sparkline=[c.close for c in done[-29:]] + [last],
                    regime=latest_regime,
                    regime_scope=scope,
                    source=tick.source if tick else "STORED",
                    last_bar_date=bars[-1].timestamp,
                    updated_at=tick.at if tick else bars[-1].timestamp,
                )
            )
        return out

    @app.get("/api/candles/{asset}", response_model=list[Candle])
    def candles(asset: Asset, limit: int | None = Query(None, ge=1)):
        bars = store.candles(asset)
        if not bars:
            raise HTTPException(404, f"No stored history for {asset.value}. Run scripts/fetch_data.py.")
        return bars[-limit:] if limit else bars

    @app.get("/api/regime", response_model=list[RegimeReading])
    def regime():
        readings = []
        for asset, scope in ((None, "SHARED"), (Asset.SILVER, "OWN")):
            by_day, _ = store.regime_by_day(asset or Asset.BTC)
            history, prev = [], None
            for d, v in sorted(by_day.items()):
                if v != prev:
                    history.append((d, v))
                    prev = v
            readings.append(
                RegimeReading(scope=scope, asset=asset, value=prev, since=history[-1][0] if history else None, history=history)
            )
        return readings

    @app.get("/api/signals/{asset}", response_model=list[Signal])
    def signals(asset: Asset):
        """Real signals that exist today: the days the regime reading turned BULL or BEAR."""
        by_day, scope = store.regime_by_day(asset)
        out, prev = [], None
        what = "BTC/ETH regime gate" if scope == "SHARED" else f"{asset.value} trend (50/200-day rule)"
        for d, v in sorted(by_day.items()):
            if prev is not None and v != prev and v in ("BULL", "BEAR"):
                out.append(
                    Signal(
                        name="regime_gate" if scope == "SHARED" else "trend",
                        asset=asset,
                        timestamp=d,
                        direction=Direction.LONG if v == "BULL" else Direction.SHORT,
                        strength=1.0,
                        reason=f"{what} turned {v} (was {prev}).",
                    )
                )
            prev = v
        return out

    # ------------------------------------------------------------ sky + transits

    def notable(event) -> list[NotableFor]:
        out = []
        for asset in ASSETS:
            pb = store.playbook(asset)
            if not pb:
                continue
            by_id = {p.pattern_id: p for p in pb.patterns}
            best = None
            for pid in patterns_for_event(event):
                r = by_id.get(pid)
                if r and RANK[r.label] >= RANK[ConfidenceLabel.WEAK] and (best is None or RANK[r.label] > RANK[best.label]):
                    best = r
            if best:
                out.append(NotableFor(asset=asset, pattern_id=best.pattern_id, label=best.label, dominant_outcome=best.dominant_outcome))
        return out

    @app.get("/api/sky", response_model=list[SkyPosition])
    def sky():
        planets = store.planets()
        if not planets:
            raise HTTPException(404, "No ephemeris stored. Run scripts/fetch_ephemeris.py.")
        from orbit.data.ephemeris import ZODIAC_SIGNS

        today = np.datetime64(today_utc().replace(tzinfo=None), "D")
        events = store.transit_events()
        out = []
        for planet, ps in planets.items():
            i = int(np.searchsorted(ps.dates, today))
            if i >= len(ps.dates):
                continue
            longitude = float(ps.longitude[i])
            upcoming = next((e for e in events if e.planet == planet and e.date >= today_utc()), None)
            out.append(
                SkyPosition(
                    planet=planet,
                    longitude=longitude,
                    sign=ZODIAC_SIGNS[int(ps.sign_index[i])],
                    degree=longitude % 30,
                    retrograde=bool(ps.retrograde[i]),
                    next_event=upcoming,
                )
            )
        return out

    @app.get("/api/transits", response_model=list[TransitView])
    def transits(
        start: datetime | None = Query(None, alias="from"),
        end: datetime | None = Query(None, alias="to"),
        include_moon: bool = False,
    ):
        lo = utc_day(start) if start else today_utc() - timedelta(days=90)
        hi = utc_day(end) if end else today_utc() + timedelta(days=180)
        return [
            TransitView(event=e, label=event_label(e), notable=notable(e))
            for e in store.transit_events()
            if lo <= e.date <= hi and (include_moon or e.planet.value != "MOON")
        ]

    # ------------------------------------------------------------ playbook

    @app.get("/api/playbook", response_model=PlaybookOverview)
    def playbook_overview():
        meta = store.playbook_meta()
        if not meta:
            raise HTTPException(404, "The playbook hasn't been built yet. Run scripts/build_playbook.py.")
        return PlaybookOverview(
            generated_at=meta["generated_at"],
            total_tests=meta["total_tests"],
            tests_by_family=meta["tests_by_family"],
            runs_so_far=int(meta["parameters"].get("runs_so_far", 1)),
            parameters=meta["parameters"],
            assets=meta["assets"],
            placebo=store.placebo(),
        )

    def _summary(r: PatternResult) -> PatternSummary:
        return PatternSummary(
            **r.model_dump(include=set(PatternSummary.model_fields) - {"exceptions"}),
            exceptions=sum(1 for o in r.occurrences if o.is_exception),
        )

    @app.get("/api/playbook/{asset}", response_model=PlaybookView)
    def playbook(asset: Asset):
        pb = store.playbook(asset)
        if not pb:
            raise HTTPException(404, f"No playbook for {asset.value} yet. Run scripts/build_playbook.py.")
        return PlaybookView(
            **pb.model_dump(include={"asset", "generated_at", "history_start", "history_end", "bars", "sideways"}),
            patterns=[_summary(r) for r in pb.patterns],
        )

    @app.get("/api/playbook/{asset}/patterns/{pattern_id}", response_model=PatternResult)
    def pattern(asset: Asset, pattern_id: str):
        pb = store.playbook(asset)
        r = next((p for p in pb.patterns if p.pattern_id == pattern_id), None) if pb else None
        if not r:
            raise HTTPException(404, f"No pattern {pattern_id} for {asset.value}.")
        return r

    # ------------------------------------------------------------ layers not built yet

    @app.get("/api/suggestions")
    def suggestions():
        return []

    @app.post("/api/suggestions/{suggestion_id}/decision", status_code=501)
    def decide(suggestion_id: str):
        raise HTTPException(501, NOT_BUILT)

    @app.get("/api/journal")
    def journal():
        return []

    @app.get("/api/drift")
    def drift():
        raise HTTPException(404, "The backtest layer isn't built yet, so there is no expected performance to compare against.")

    # ------------------------------------------------------------ system

    @app.get("/api/system", response_model=SystemStatus)
    def system():
        beat = read_status()
        if beat is None:
            runner = RunnerStatus(state="NEVER_RUN")
        else:
            runner = RunnerStatus(**{k: beat.get(k) for k in RunnerStatus.model_fields if k != "state" and k in beat}, state="STALE")
            last = runner.last_cycle_finished_at or runner.started_at
            grace = timedelta(seconds=2 * (runner.interval_seconds or settings.RUNNER_INTERVAL_SECONDS) + 600)
            if last and datetime.now(timezone.utc) - last < grace:
                runner.state = "LIVE"
        report = store.history_report()
        feeds = []
        for asset in ASSETS:
            bars = store.candles(asset)
            rep = report.get(asset.value, {})
            tick = feed.latest.get(asset)
            feeds.append(
                FeedStatus(
                    asset=asset,
                    sources=[s["source"] for s in rep.get("sources", [])] or sorted({c.source for c in bars if c.source}),
                    first_bar=bars[0].timestamp if bars else None,
                    last_bar=bars[-1].timestamp if bars else None,
                    bars=len(bars),
                    live_source=tick.source if tick else "STORED",
                    last_tick_at=tick.at if tick else None,
                )
            )
        meta = store.playbook_meta()
        return SystemStatus(
            runner=runner,
            components=Components(runner=beat is not None, playbook=meta is not None, strategy=False, journal=False, backtest=False, alerts=False),
            strategy=None,
            timeframe=settings.TIMEFRAME,
            auto_execution=False,
            feeds=feeds,
            log=[LogLine(timestamp=t, level=l, message=m) for t, l, m in store.runner_log()],
            config={
                "TRACKED_ASSETS": " ".join(settings.TRACKED_ASSETS),
                "TIMEFRAME": settings.TIMEFRAME,
                "RUNNER_INTERVAL_SECONDS": str(settings.RUNNER_INTERVAL_SECONDS),
                "HISTORY_START": ", ".join(f"{k} {v}" for k, v in settings.HISTORY_START.items()),
                "MIN_OCCURRENCES": str(settings.MIN_OCCURRENCES),
                "BIG_MOVE_PERCENTILE": str(settings.BIG_MOVE_PERCENTILE),
                "FDR (strong / moderate)": f"{settings.FDR_STRONG} / {settings.FDR_MODERATE}",
                "TELEGRAM_BOT_TOKEN": "set" if settings.TELEGRAM_BOT_TOKEN else "not set",
            },
            playbook_generated_at=meta["generated_at"] if meta else None,
        )

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        await feed.serve(socket)

    return app


app = create_app()
