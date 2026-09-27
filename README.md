# Orbit — Systematic Trading Strategy

A 24/7 systematic trading assistant for **BTC, ETH, SOL, and Silver**. It watches markets continuously and suggests trades with a stated confidence level — it does not place trades on its own (yet). The plan is to earn trust in the system over time before ever turning on auto-execution.

This project doubles as a learning project. Every module is built to be understandable, not just functional — comments and docs explain *why*, not just *what*.

## Core ideas

- **One strategy at a time** — no juggling multiple competing strategies until one is proven.
- **Your experience becomes rules** — trading intuition gets written down as explicit, testable logic instead of staying a "feeling."
- **Self-correcting** — the system tracks its own live performance against what backtesting predicted, and flags itself (or scales down) when reality drifts from expectation.
- **Suggestions, not autopilot** — every trade idea comes with its reasoning, for you to approve, until auto-execution is explicitly turned on later.

## Project layout

```
orbit/
  src/orbit/
    data/          # fetch + store price & ephemeris data (stitched full histories)
    features/      # raw data -> signals (indicators, regime, astro transits)
    analysis/      # transit research: events, outcomes, significance, the playbook
    api/           # HTTP + WebSocket API the web terminal reads
    strategy/       # the one active strategy: entry/exit/risk rules
    backtest/       # historical simulation + walk-forward validation
    journal/        # trade log schema + read/write
    runner/          # 24/7 loop: schedule -> evaluate -> alert
    alerts/          # Telegram/console notifier
    config/          # settings (assets, timeframe, secrets via .env)
    core/            # shared types used everywhere (Candle, Signal, Trade, ...)
  web/               # React trading terminal (see web/README.md)
    src/api/         # API client; types mirrored from core/types.py and api/schemas.py
    src/panels/      # one screen per terminal function (chart, watchlist, suggestions, ...)
  tests/             # mirrors src/orbit structure
  scripts/           # one-off manual scripts
  data/              # local price history, ephemeris, features, playbook output (gitignored)
```

`strategy/`, `backtest/`, `journal/` and `alerts/` are still empty stubs — see Status below for what's actually built.

## Getting started

```bash
git clone https://github.com/withaphelion-afk/orbit.git
cd orbit
uv sync --extra dev
uv run pytest -q
```

That installs dependencies into a local `.venv` and confirms the test suite passes. Copy `.env.example` to `.env` and fill in secrets (e.g. Telegram bot token) only when you actually need them — nothing requires secrets yet.

Then build the local data. None of these steps needs an API key:

```bash
uv run python scripts/fetch_data.py        # full price history; the first run takes ~30s, later runs fetch only new bars
uv run python scripts/fetch_ephemeris.py   # planetary positions, 60 years back and 2 ahead
uv run python scripts/compute_features.py  # technical, regime and astro features
uv run python scripts/build_playbook.py    # transit playbook (~25s)
uv run python scripts/placebo_check.py     # optional sanity check of the playbook method (~2 min)
uv run python -m orbit.api                 # API for the web terminal, on http://127.0.0.1:8000
```

**Note for Windows machines with Smart App Control / Application Control:** it blocks pandas' compiled files, so nothing in `src/` imports pandas; the maths uses numpy, which loads fine.

### Web terminal

The UI is a separate React app in `web/`, and it needs Node 20.19+ or 22.12+. It reads everything from the API above, so start that first:

```bash
cd web
npm install
npm run dev      # http://localhost:5173
npm test         # unit tests
```

It opens on the monitor screen: a chart on the left and the watchlist on the right. Press `F1` for every command and key.

- **Everything shown is real:** live prices from Binance (silver delayed, from Yahoo), the stored histories, the regime gate, planet positions, the transit playbook and runner status. There is no mock data.
- **Chart:** LIVE mode is TradingView's embedded chart with their own data. ORBIT mode draws the full stored history with regime flips and transit markers.
- **Layers not built yet** (strategy, journal, backtest) show an explicit "not built yet" screen. They fill in by themselves once the API reports those layers as built.

See [`web/README.md`](web/README.md) for the screens and the API contract.

## For contributors (including other Claude sessions)

Read in this order before starting work:

1. **This README** — what the project is, how it's laid out, and the full plan below.
2. **`git log`** — recent commits explain what's actually been built vs. planned.
3. **`src/orbit/core/types.py`** — the shared vocabulary (`Candle`, `Signal`, `TradeSuggestion`, `JournalEntry`, `Regime`) every module is built around.
4. **`web/README.md`** — if you're touching the UI or building the API it reads from.

Design principles to keep in mind while contributing:
- One strategy at a time — don't build a plugin system for hypothetical future strategies.
- Config lives in `config/settings.py`, not hardcoded in modules.
- Keep modules independently testable: pure functions where possible (`data/` returns candles, `features/` turns candles into signals, `strategy/` turns signals into trade suggestions).
- `web/src/api/types.ts` mirrors `core/types.py` field for field. When you change a core type, change it there too.

This README is the single source of truth for planning — update it in place when a phase's status changes, instead of writing the plan elsewhere.

## Status

- `core/types.py` — shared data model (`Candle`, `Signal`, `TradeSuggestion`, `JournalEntry`, `Regime`, `EphemerisSnapshot`, `FeatureRecord`) — done.
- `data/history.py` — full daily history per asset, stitched across venues and then updated incrementally — done.
  - BTC: Bitstamp from 2013, then Binance from Aug 2017.
  - ETH: Coinbase from May 2016, then Binance from Aug 2017.
  - SOL: Binance from Aug 2020.
  - Silver: Yahoo futures from Aug 2000.
  - Before joining two venues it checks that their closes agree over the overlap (currently a median gap of about 0.45%) and refuses if they don't. Every bar records its source, and each build writes `data/history_report.json`.
  - Fetchers live in `data/binance.py`, `bitstamp.py`, `coinbase.py` and `silver.py`, sharing a retrying HTTP helper. Run with `uv run python scripts/fetch_data.py`.
- `data/ephemeris.py` — daily planetary positions (zodiac sign + retrograde) via Skyfield, 60 years back and 2 years ahead, dated at UTC midnight like the prices — done. Run with `uv run python scripts/fetch_ephemeris.py`.
- `data/storage.py` — save/load candles and ephemeris snapshots as CSV under `data/` — done.
- `features/store.py` — the feature store: append-only CSV per asset, long format (date, name, value) — done.
- `features/technical.py` — daily return, close vs. 50/200-day SMA, 20-day volatility, computed as numpy rolling windows so full histories stay fast — done.
- `features/regime.py` — the regime gate (BTC+ETH 50/200-day SMA trend, both must agree for BULL/BEAR or it's CHOPPY) plus `compute_regime_series` to log its full history, not just a live reading — done.
- `features/astro.py` — encodes ephemeris sign/retrograde as numeric features per tracked asset — done.
- `scripts/compute_features.py` — runs the full pipeline (technical + regime + astro) into the feature store — done, verified against real data (BTC/ETH/SOL/silver, 60 years of ephemeris).
- `data/pipeline.py` + `features/pipeline.py` — the fetch and feature-computation steps, refactored into reusable functions so scripts and the runner share the same logic.
- `runner/loop.py` — the 24/7 loop: on an interval, fetches fresh data, recomputes features, and logs the current regime. Wrapped so a single failed cycle (network blip, rate limit) is logged and retried, never crashes the process. It writes a heartbeat (`data/runner_status.json`) that the API reports — done, verified against real data end to end.
- `analysis/` — the transit playbook: sign ingresses and retrograde stations, outcomes over several forward horizons, significance tests, confidence labels, exception context and a chop track — done. See "Astro-transit research track" below for method and findings. Run with `uv run python scripts/build_playbook.py`.
- `api/` — FastAPI server the web terminal reads: stored data, the playbook, runner status, and live prices over `/ws` — done. Run with `uv run python -m orbit.api`.
- `web/` — the React trading terminal, on real data only — done. It has a command line with a Ctrl+K palette and F-key screens:
  - MON: chart and watchlist
  - GP: live TradingView chart, or Orbit's full-history chart with regime and transit markers
  - ASTRO: current sky, transit calendar, playbook and chop track
  - SYS: runner, layers, feeds, log and config
  - SUGG, JRNL and DRIFT are ready but show "not built yet" until those layers exist
- Per-asset entry scoring, the actual strategy rules, backtesting, and the journal — not started yet.

### Running the 24/7 runner

```bash
uv run python -m orbit.runner.loop
```

Runs forever, re-checking every hour by default (`RUNNER_INTERVAL_SECONDS` in `config/settings.py` — daily candles don't produce new data more often than that anyway). Logs go to console and `data/logs/runner.log`. This process needs to actually stay running somewhere — for now that's a terminal you leave open; the "VPS vs home server" open decision below is about making that permanent.

### Running the web API (backend for the React frontend)

```bash
uv run python -m orbit.api        # or, while developing: uv run uvicorn orbit.api.app:app --reload
```

Serves on `http://127.0.0.1:8000` by default, matching what `web/vite.config.ts` proxies `/api` and `/ws` to. Run `scripts/fetch_data.py`, `scripts/fetch_ephemeris.py` and `scripts/build_playbook.py` first (see Getting started) so there's real data for it to serve. The web terminal always reads this API; there is no mock mode.

It only reads what the scripts and runner have stored; it never fetches history or runs research itself. The one exception is live prices: a background task polls Binance and Yahoo (for silver) and pushes each tick over `/ws`.

**Layers that don't exist yet answer honestly:**
- `/api/suggestions` and `/api/journal` return `[]`.
- A decision POST returns `501`.
- `/api/drift` returns `404`, with an explanation.
- `/api/system` lists which layers are built, so the UI can say "not built yet" rather than show empty numbers.

## Full plan

### Strategy structure for crypto (BTC/ETH/SOL)

A shared *regime gate* computed from BTC (and ETH) decides whether the environment favors longs, shorts, or no trade at all — this stops the system from fighting the macro trend. A *per-asset entry layer* sits on top, scoring each coin's own relative strength/setup for actual entry timing, so genuine divergence (e.g. SOL breaking out while BTC chops) still gets caught. Silver is fully separate — no crypto correlation logic applies to it. Position sizing must treat correlated crypto longs/shorts as one grouped exposure, not three independent bets.

### System architecture

| Layer | Purpose |
| --- | --- |
| Data layer | Pull OHLCV for BTC/ETH/SOL (exchange APIs) and silver (broker/vendor feed) + ephemeris data; store in a time-series DB |
| Feature/signal engineering | Technical indicators, regime detection, plus astro-transit features |
| Scoring engine | Rules-based scorecard first; ML model added later once enough logged trades exist |
| Risk & portfolio management | Position sizing, exposure/correlation limits, stop-loss/target, drawdown circuit breaker |
| Backtesting | Walk-forward validated backtests before anything goes live |
| 24/7 runner | Always-on scheduler that re-evaluates the strategy on an interval |
| Alerting | Pushes trade suggestions with reasoning (Telegram/dashboard) — no execution yet |
| Web terminal | Keyboard-first dashboard (`web/`) to review suggestions with their reasoning and log take/skip/modify decisions to the journal |
| Feedback loop | Trade journal of every suggestion + decision + outcome, used to periodically reweight the scorecard |

### Astro-transit research track

Treated as one testable input among others — back-tested with the same rigor as technical signals, not taken on faith.

- **Ephemeris source**: Skyfield (pure Python, no compiler needed) — exact planetary positions/transits for any date, free, precise. (Originally planned as Swiss Ephemeris via `pyswisseph`, but that needs a C++ compiler not available on this machine.)
- **Event tagging**: a table of historical transit events (sign changes, retrogrades, conjunctions/aspects) mapped to date ranges, joined against price history to compute frequency, average move and win rate after each event type.
- **Significance testing**: long-cycle transits (e.g. Jupiter ~12 years) give very few historical samples — explicitly test whether any correlation is statistically real or noise before trusting it.
- **Status**: the transit playbook is built (`analysis/`, `scripts/build_playbook.py`).
- **Events**: sign ingresses (first entries tested; backward ingresses and re-entries recorded but not double-counted) and retrograde stations (the retrograde flag with one- and two-day flickers removed). Aspects and conjunctions are deferred.
- **Outcomes**: forward returns over horizons that depend on planet speed:
  - Moon: 1, 3 and 5 bars
  - Sun to Mars: 1, 5, 10 and 20 bars
  - Jupiter outward: 20, 40 and 60 bars

  Each is labelled against the asset's *own* history: BIG_UP or BIG_DOWN for its top or bottom 15% of returns at that horizon; SIDEWAYS for a small net move (measured against ATR) while the market still moved normally; NEUTRAL otherwise.
- **Significance**:
  - Each pattern's hit rate is compared with the whole event calendar circularly shifted against the prices, over every shift at least 30 bars away (computed at once via FFT). This keeps both the events' spacing and the market's trends intact.
  - Where the shifts run out of resolution, a negative-binomial tail fitted to the shifted results takes over.
  - An exact check against uniformly random dates (hypergeometric) is reported alongside, not corrected.
  - Benjamini-Hochberg FDR corrects all of an asset's pattern tests as one family.
  - Patterns with fewer than 12 occurrences are never tested.
  - The hypothesis list is written before any test runs, and every run is logged.
- **Labels**: strong (q ≤ 0.05, 25+ occurrences, 1.5× the base rate), moderate (q ≤ 0.10), weak (nominal p < 0.05 only), none, insufficient_data.
- **Exceptions**: every occurrence that went against its pattern's dominant outcome is listed with its context:
  - the regime at the time (the shared gate for crypto, silver's own trend)
  - the volatility percentile
  - other transits in the same window, and any that lean the opposite way
- **Chop track**: separately, which transit *states* (e.g. "Mercury retrograde", "Saturn in Pisces") coincide with sideways markets. The sample size counted is distinct episodes, not days.
- **Validation**: `scripts/placebo_check.py` moves every transit date by arbitrary offsets and re-runs everything; any moderate or strong result on those fake calendars is a false discovery.
  - The first version produced false discoveries in 6 of 32 placebo runs, caused by separate correction families and a normal-curve tail. Both were fixed.
  - It now produces 0 of 32.
  - A planted-effect unit test confirms the method still catches a real effect.
- **Findings so far (Sept 2026)**: 2,241 tests across four assets.
  - **No transit pattern survives multiple-testing correction for any asset.** That is 0 strong and 0 moderate.
  - Some patterns are "weak": nominally significant, but at a rate consistent with chance (about 3–6% of tests fall below p < 0.05). They're worth watching, not trading.
  - Slow planets (Jupiter outward) almost never reach the 12-occurrence minimum in crypto histories, which is the expected, honest outcome.
  - The playbook re-runs as data grows. A pattern only counts once it clears the correction.

### Signal research reference

Notes from researching how professional quant systems structure this, so we build on established practice instead of guesswork:

- **Signal categories worth having**: price-action/technical (momentum, mean reversion, volatility), volume/liquidity, on-chain (crypto: exchange flows, MVRV, SOPR), derivatives positioning (crypto: funding rate, open interest), macro (silver: real yields, DXY, gold/silver ratio), positioning (silver: CFTC COT report — released with a lag, watch for look-ahead bias), cross-asset correlation.
- **Telling a real signal from noise**: keep out-of-sample data untouched until final testing; use walk-forward validation (fit on a rolling past window, test on the next period, roll forward); watch for look-ahead bias (only use data available at decision time); correct for multiple testing — the more variants tried, the more likely the best result is luck (a new factor should arguably clear a t-stat of 3.0, not 2.0). For small-sample effects like astro transits specifically: write the hypothesis down *before* looking at the data, log every transit tested as a trial count, use permutation tests (shuffle event dates thousands of times, see how often random dates beat the real result), and treat ~10-30 historical events as "worth monitoring," never "proven."
- **Combining signals**: convert each to a z-score (standard deviations from its own average) and combine with weights close to equal — optimized weights tend to overfit. Uncorrelated signals add real value; five signals all measuring momentum are worth about one. Regime-conditional models (classify the market state first, then decide which signals/exposures apply) are the standard structure — confirms our regime-gate + per-asset-entry design matches how real quant shops work. One caveat: regime classifiers are slow to recognize a *new* regime, so the gate itself needs testing too, not just what sits on top of it.
- **Feature store concept**: a central, timestamped table of computed signals sitting between raw data and strategy logic — ingestion writes raw data, features are computed once and "point-in-time correct" (timestamped with when they'd actually have been knowable), and strategies only ever read features, never raw data directly. Stops indicators being recomputed slightly differently in different places and prevents look-ahead leakage. This is the model for our own `features/` layer.

### Build plan

| Phase | Description | Status |
| --- | --- | --- |
| 1. Define the strategy | Assets, timeframe, entry/exit rules, risk rules on paper | Not started |
| 2. Data pipeline | Price data + ephemeris data, stored locally | Done: full stitched histories, incremental updates, ephemeris 2 years ahead |
| 3. Backtest engine | Walk-forward validation; test astro factors for significance | Astro factors tested (transit playbook, placebo-checked); backtest engine itself not started |
| 4. Trade journal + scorecard | Logging schema for every signal and decision | Not started |
| 5. 24/7 runner | Always-on service, evaluates on schedule, logs/alerts, no execution | Loop, logging and heartbeat built; alerting not started; not yet deployed to run unattended |
| 6. Feedback loop | Review cadence to correct/reweight the scorecard | Not started |
| 7. Auto-execution | Enabled later, once confidence is earned | Not started |
| Web terminal | Dashboard for suggestions, decisions, journal, drift and runner status | Built on real data via `api/`; suggestion, journal and drift screens wait on their layers |

### Open decisions

- **Project name**: working title **Orbit** (used for the astro-transit + always-on-monitoring theme).
- **Strategy definition**: exact assets/timeframe/entry-exit rules for the single strategy — not yet locked; deliberately deferred while the data layer gets built out first.
- **Hosting for the 24/7 runner**: VPS vs home server — not yet decided.
- **Journal fields**, to settle when `journal/` is built:
  - Is `JournalEntry.outcome_pnl` a percent return? The UI assumes it is.
  - The API's journal rows add `counterfactual_pnl`: what a skipped suggestion would have returned.
- **Playbook schedule**: `scripts/build_playbook.py` runs on its own, daily or weekly, not inside the hourly runner. How it gets scheduled on the eventual host goes with the hosting decision.
