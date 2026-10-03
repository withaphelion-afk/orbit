"""The HTTP + WebSocket API the web terminal reads. Run with:

    uv run python -m orbit.api

Read-only over stored data (see store.py) plus a live price feed (live.py),
except two writes: starting an analysis run, and logging your decision on a
suggestion (which goes to the journal, never to an exchange). Reports that
haven't been generated yet answer 404, and /api/system says which components
exist so the UI can show why.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from orbit.config import settings
from orbit.core.types import (
    Asset,
    Candle,
    ConfidenceLabel,
    Decision,
    Direction,
    PatternResult,
    Planet,
    ProjectionTrack,
    Signal,
    SpeedClass,
    TransitEventType,
)
from orbit.data.dates import today_utc, utc_day
from orbit.api import store
from orbit.api.live import LiveFeed
from orbit.analysis import jobs
from orbit.analysis.jobs import AnalysisRun
from orbit.api.schemas import (
    Components,
    DecisionRequest,
    DivergenceLabelRequest,
    DriftReport,
    JournalRow,
    SuggestionView,
    FeedStatus,
    LogLine,
    NotableFor,
    PatternSummary,
    PlaybookOverview,
    PlaybookView,
    ProjectionView,
    Quote,
    RegimeReading,
    RunnerStatus,
    RunRequest,
    ScheduleView,
    SkyPosition,
    SystemStatus,
    TransitView,
)
from orbit.analysis.confidence import RANK
from orbit.analysis.patterns import patterns_for_event
from orbit.analysis.projections import DAYS_AHEAD, build_projections, current_conditions, headline_stat
from orbit.analysis.transit_events import event_label
from orbit.runner.status import read_status
from orbit.backtest.engine import NAME as STRATEGY_NAME
from orbit.vedic.patterns import speed_class

ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL, Asset.SILVER]
WEB_DIST = settings.REPO_ROOT / "web" / "dist"
LIVE_FRESH = timedelta(minutes=5)


def _journal_row(r) -> JournalRow:
    expired = r.status == "expired"
    entry = r.journal_entry()
    if expired:
        entry = entry.model_copy(update={"decision": Decision.SKIPPED, "notes": "No decision in time: expired, logged as skipped."})
    skipped = expired or r.decision == Decision.SKIPPED
    out = r.acted if r.decision in (Decision.TAKEN, Decision.MODIFIED) else r.paper
    return JournalRow(
        id=r.id,
        decided_at=r.decided_at or r.created_at,
        entry=entry,
        expired=expired,
        counterfactual_pnl=r.paper.return_pct if skipped and r.paper else None,
        exit_reason=out.reason if out else None,
        timeframe=r.timeframe,
    )


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
        """The daily divergences that alerted (dated to their confirmation bar), plus the days the regime turned BULL or BEAR."""
        from orbit.strategy import divergence_model as dm

        out = []
        for c in ((dm.load_recent() or {}).get("candidates", {}).get(asset.value, {}).get("1d", [])):
            if c.get("alert"):
                out.append(
                    Signal(
                        name="rsi_divergence",
                        asset=asset,
                        timestamp=datetime.fromtimestamp(c["confirmed_at"], tz=timezone.utc),
                        direction=Direction(c["direction"]),
                        strength=float(min(1.0, c["score"] or 0)),
                        reason=f"{c['kind'].capitalize()} {'bullish' if c['direction'] == 'LONG' else 'bearish'} RSI divergence, score {c['score']:.0%}",
                    )
                )
        by_day, scope = store.regime_by_day(asset)
        prev = None
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
        return sorted(out, key=lambda g: g.timestamp)

    # ------------------------------------------------------------ sky + transits

    def rated_patterns() -> dict[Asset, dict[str, PatternResult]]:
        """Each asset's patterns rated weak or better, by id (all a transit list needs to look up)."""
        out = {}
        for asset in ASSETS:
            pb = store.playbook(asset)
            if pb:
                out[asset] = {p.pattern_id: p for p in pb.patterns if RANK[p.label] >= RANK[ConfidenceLabel.WEAK]}
        return out

    def notable(event, rated: dict[Asset, dict[str, PatternResult]] | None = None) -> list[NotableFor]:
        rated = rated if rated is not None else rated_patterns()
        out = []
        pids = patterns_for_event(event)
        for asset, by_id in rated.items():
            best = None
            for pid in pids:
                r = by_id.get(pid)
                if r and (best is None or RANK[r.label] > RANK[best.label]):
                    best = r
            if best:
                out.append(NotableFor(asset=asset, pattern_id=best.pattern_id, label=best.label, dominant_outcome=best.dominant_outcome))
        return out

    @app.get("/api/sky", response_model=list[SkyPosition])
    def sky():
        """The 9 grahas right now, in the sidereal zodiac (Vedic rules)."""
        from orbit.vedic import zodiac as z
        from orbit.vedic.sky import sidereal_longitude, speed, tt_of, wrap

        now = datetime.now(timezone.utc)
        tt = tt_of(now)
        sun = float(sidereal_longitude(Planet.SUN, tt)[0])
        upcoming = [e for e in store.transit_events() if e.exact_time and e.exact_time >= now
                    and e.event_type in (TransitEventType.INGRESS, TransitEventType.STATION_RETROGRADE, TransitEventType.STATION_DIRECT)]
        out = []
        for g in z.GRAHAS:
            lon = float(sidereal_longitude(g, tt)[0])
            rashi = int(lon // 30)
            nak = int(lon // z.NAKSHATRA_SPAN)
            vakri = g in z.NODES or float(speed(g, tt)[0]) < 0
            orb = (z.COMBUSTION_ORB_VAKRI if vakri else {}).get(g, z.COMBUSTION_ORB.get(g))
            mover = Planet.RAHU if g == Planet.KETU else g
            out.append(
                SkyPosition(
                    planet=g,
                    name=z.NAMES[g],
                    longitude=lon,
                    sign=z.rashi_label(rashi),
                    degree=lon % 30,
                    nakshatra=z.NAKSHATRAS[nak],
                    pada=int((lon % z.NAKSHATRA_SPAN) // (z.NAKSHATRA_SPAN / 4)) + 1,
                    retrograde=vakri,
                    combust=bool(orb and abs(float(wrap(lon - sun))) < orb),
                    dignity=z.dignity(g, rashi),
                    next_event=next((e for e in upcoming if e.planet == mover), None),
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
        rated = rated_patterns()
        return [
            TransitView(event=e, label=event_label(e), notable=notable(e, rated))
            for e in store.transit_events()
            if lo <= e.date <= hi and (include_moon or speed_class(e) != SpeedClass.LUNAR)
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
            **pb.model_dump(include={"asset", "generated_at", "history_start", "history_end", "bars", "hourly_start", "hourly_bars", "sideways"}),
            patterns=[_summary(r) for r in pb.patterns],
        )

    @app.get("/api/playbook/{asset}/patterns/{pattern_id}", response_model=PatternResult)
    def pattern(asset: Asset, pattern_id: str):
        pb = store.playbook(asset)
        r = next((p for p in pb.patterns if p.pattern_id == pattern_id), None) if pb else None
        if not r:
            raise HTTPException(404, f"No pattern {pattern_id} for {asset.value}.")
        return r

    # ------------------------------------------------------------ projections

    @app.get("/api/projections", response_model=list[ProjectionView])
    def projections(days: int = Query(DAYS_AHEAD, ge=1, le=730), include_none: bool = False):
        """Upcoming events joined to each asset's playbook evidence. Weak and none rows are
        unproven (trusted=false); insufficient_data is never projected."""
        playbooks = {a: pb for a in ASSETS if (pb := store.playbook(a)) is not None}
        if not playbooks:
            raise HTTPException(404, "No playbook yet, so there is no evidence to project from. Run the analysis (or scripts/build_playbook.py).")
        conditions = {}
        for asset in playbooks:
            by_day, _ = store.regime_by_day(asset)
            conditions[asset] = current_conditions(store.price_series(asset), by_day[max(by_day)] if by_day else None)
        rows = build_projections(store.transit_events(), playbooks, datetime.now(timezone.utc), days, include_none, conditions)
        results = {a: {r.pattern_id: r for r in pb.patterns} for a, pb in playbooks.items()}
        return [ProjectionView(**dict(p), horizon_stat=headline_stat(results[p.asset][p.pattern_id])) for p in rows]

    @app.get("/api/projections/track", response_model=ProjectionTrack)
    def projections_track():
        """How recorded projections turned out once their windows closed, by label, beside chance."""
        return store.projection_track()

    # ------------------------------------------------------------ strategy, journal, backtest

    @app.get("/api/suggestions", response_model=list[SuggestionView])
    def suggestions():
        """Suggestions waiting for your decision, newest first."""
        from orbit.journal import store as journal_store

        pending = [r for r in journal_store.load() if r.status == "pending"]
        return [
            SuggestionView(id=r.id, created_at=r.created_at, risk_reward=r.risk_reward, suggestion=r.suggestion, timeframe=r.timeframe)
            for r in sorted(pending, key=lambda r: r.created_at, reverse=True)
        ]

    @app.post("/api/suggestions/{suggestion_id}/decision", response_model=JournalRow)
    def decide(suggestion_id: str, req: DecisionRequest):
        """Log what you did with a suggestion. This writes the journal; it never places an order."""
        from orbit.strategy import live as live_strategy

        if req.decision == Decision.MODIFIED and None in (req.entry_price, req.stop_loss, req.take_profit):
            raise HTTPException(422, "MODIFIED needs entry_price, stop_loss and take_profit.")
        try:
            rec = live_strategy.decide(suggestion_id, req.decision, req.notes, req.entry_price, req.stop_loss, req.take_profit)
        except KeyError:
            raise HTTPException(404, f"No suggestion {suggestion_id}.")
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return _journal_row(rec)

    @app.get("/api/journal", response_model=list[JournalRow])
    def journal():
        """Every suggestion you decided on, plus the ones that expired undecided, newest first."""
        from orbit.journal import store as journal_store

        rows = [_journal_row(r) for r in journal_store.load() if r.status != "pending"]
        return sorted(rows, key=lambda r: r.decided_at, reverse=True)

    @app.get("/api/drift", response_model=DriftReport)
    def drift(timeframe: str = Query("1d", pattern="^(4h|1d)$")):
        from orbit.backtest.drift import report

        rep = report(timeframe)
        if rep is None:
            raise HTTPException(404, "No backtest yet, so there is no expected performance to compare against. Run the analysis.")
        return rep

    @app.get("/api/backtest")
    def backtest_summary():
        from orbit.backtest.engine import load

        rep = load()
        if rep is None:
            raise HTTPException(404, "No backtest yet. Run the analysis (it backtests the strategy every run).")
        return rep

    @app.get("/api/backtest/{asset}")
    def backtest_asset(asset: Asset, timeframe: str = Query("1d", pattern="^(4h|1d)$")):
        from orbit.backtest.engine import load

        rep = load(asset.value, timeframe)
        if rep is None:
            raise HTTPException(404, f"No backtest for {asset.value} yet.")
        return rep

    @app.get("/api/calibration")
    def calibration():
        """The feedback loop: the learned divergence model, and whether it has proven itself out-of-sample."""
        from orbit.strategy.divergence_model import load_model

        rep = load_model()
        if rep is None:
            raise HTTPException(404, "The divergence model hasn't been trained yet. It trains on every runner cycle.")
        return {
            **{k: v for k, v in rep.items() if k != "model"},
            # the names the FEEDBACK screen has always read
            "n_backtest": rep["n_market"], "n_live": rep["n_user"], "base_win_rate": rep["base_rate"], "skill": rep["trusted"],
        }

    # ------------------------------------------------------------ divergences: candidates, model weights, alerts, your labels

    @app.get("/api/divergences/model")
    def divergence_model_weights():
        """What the browser needs to score live divergences exactly as the backend does."""
        from orbit.strategy.divergence_model import load_model

        rep = load_model()
        if rep is None:
            raise HTTPException(404, "The divergence model hasn't been trained yet. It trains on every runner cycle.")
        return {k: rep.get(k) for k in ("trained_at", "features", "model", "thresholds", "trusted", "base_rate", "agreement", "by_timeframe")}

    @app.get("/api/divergences/{asset}")
    def divergences(asset: Asset, timeframe: str | None = None):
        """Recent divergence candidates (last 1,000 bars per timeframe), scored, with outcomes and your labels."""
        from orbit.strategy.divergence_model import load_recent

        rec = load_recent()
        if rec is None:
            raise HTTPException(404, "No divergences yet. The runner finds them on its next cycle.")
        by_tf = rec["candidates"].get(asset.value, {})
        return {"generated_at": rec["generated_at"], "trusted": rec["trusted"], "thresholds": rec["thresholds"],
                "candidates": {tf: v for tf, v in by_tf.items() if timeframe in (None, tf)}}

    @app.get("/api/bars/{asset}")
    def chart_bars(asset: Asset, timeframe: str = Query("1d", pattern="^(1h|4h|1d|1w)$"), limit: int = Query(1000, ge=50, le=5000)):
        """The last `limit` completed bars at 1H/4H/1D/1W as [time, open, high, low, close, volume] rows (time: epoch seconds)."""
        from orbit.strategy import bars as bars_mod

        b = bars_mod.load(asset, timeframe).tail(limit)
        return [[int(b.time[k]), float(b.open[k]), float(b.high[k]), float(b.low[k]), float(b.close[k]), float(b.volume[k])] for k in range(len(b))]

    @app.get("/api/alerts")
    def alerts(days: int = Query(14, ge=1, le=365)):
        """Confirmed divergences that scored above their timeframe's threshold, newest first."""
        from orbit.strategy.divergence_model import load_recent

        rec = load_recent() or {"candidates": {}, "trusted": False}
        since = datetime.now(timezone.utc).timestamp() - days * 86400
        out = [{**c, "asset": a, "timeframe": tf, "trusted": rec["trusted"]}
               for a, by_tf in rec["candidates"].items() for tf, cands in by_tf.items() for c in cands
               if c.get("alert") and (c.get("confirmed_at") or 0) >= since]
        return sorted(out, key=lambda c: -c["confirmed_at"])

    @app.post("/api/divergences/label")
    def label_divergence(req: DivergenceLabelRequest):
        """Your ✓ real / ✗ not real on a divergence (or one it missed). Counts more than the market's grade on the next retrain."""
        from orbit.strategy.divergence_model import add_label

        try:
            return add_label(req.asset.value, req.timeframe, req.t1, req.t2, req.direction, req.verdict, req.note, req.source)
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.get("/api/model/{asset}")
    def astro_model(asset: Asset):
        """Does knowing the Vedic sky improve a price-only forecast? Walk-forward, with controls."""
        from orbit.analysis.model import load

        rep = load(asset)
        if rep is None:
            raise HTTPException(404, f"The Vedic model for {asset.value} hasn't been evaluated yet. Run the analysis.")
        return rep

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
            components=Components(
                runner=beat is not None, playbook=meta is not None, strategy=True, journal=True, backtest=store.backtest_exists(), alerts=False
            ),
            strategy=STRATEGY_NAME,
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

    # ------------------------------------------------------------ analysis runs

    @app.post("/api/analysis/runs", status_code=202, response_model=AnalysisRun)
    def start_run(req: RunRequest):
        try:
            return jobs.start("manual", include_placebo=req.placebo, refresh_data=req.refresh)
        except jobs.AlreadyRunning as exc:
            raise HTTPException(409, f"A run is already {exc.run.status} (started {exc.run.created_at:%H:%M} UTC). Wait for it to finish.")

    @app.get("/api/analysis/runs", response_model=list[AnalysisRun])
    def list_runs(limit: int = Query(20, ge=1, le=100)):
        return [r.model_copy(update={"log": r.log[-40:]}) for r in jobs.list_runs(limit)]

    @app.get("/api/analysis/runs/current", response_model=AnalysisRun | None)
    def current_run():
        return jobs.current()

    @app.get("/api/analysis/runs/{run_id}", response_model=AnalysisRun)
    def get_run(run_id: str):
        run = jobs.load(run_id)
        if not run:
            raise HTTPException(404, f"No analysis run {run_id}.")
        return run

    @app.get("/api/analysis/schedule", response_model=ScheduleView)
    def analysis_schedule():
        beat = read_status() or {}
        last = jobs.last_successful()
        return ScheduleView(
            enabled=settings.ANALYSIS_SCHEDULE_ENABLED,
            daily_at_utc=settings.ANALYSIS_DAILY_AT_UTC,
            placebo_weekday=settings.PLACEBO_WEEKDAY,
            next_at=beat.get("next_analysis_at"),
            runner_running=beat != {},
            last_success_at=last.finished_at if last else None,
            last_success_trigger=last.trigger if last else None,
        )

    # ------------------------------------------------------------ hourly drill-down

    @app.get("/api/intraday/{asset}", response_model=list[Candle])
    def intraday(
        asset: Asset,
        at: datetime = Query(..., description="centre of the window, e.g. a transit's exact moment"),
        before_hours: int = Query(72, ge=0, le=24 * 30),
        after_hours: int = Query(24 * 10, ge=1, le=24 * 60),
    ):
        bars = store.candles(asset, "1h")
        if not bars:
            raise HTTPException(404, f"No hourly history for {asset.value} yet. Run scripts/fetch_data.py (silver: scripts/backfill_silver.py).")
        at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
        lo, hi = at - timedelta(hours=before_hours), at + timedelta(hours=after_hours)
        import bisect

        times = [c.timestamp for c in bars]
        return bars[bisect.bisect_left(times, lo) : bisect.bisect_right(times, hi)]

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        await feed.serve(socket)

    # The built web terminal (npm run build -> web/dist), so everyday use is one
    # address and no dev server. Mounted last so every /api and /ws route wins.
    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")

    return app


app = create_app()
