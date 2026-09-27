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
    data/          # fetch + store price & ephemeris data
    features/      # raw data -> signals (indicators, regime, astro transits)
    strategy/       # the one active strategy: entry/exit/risk rules
    backtest/       # historical simulation + walk-forward validation
    journal/        # trade log schema + read/write
    runner/          # 24/7 loop: schedule -> evaluate -> alert
    alerts/          # Telegram/console notifier
    config/          # settings (assets, timeframe, secrets via .env)
    core/            # shared types used everywhere (Candle, Signal, Trade, ...)
  tests/             # mirrors src/orbit structure
  scripts/           # one-off manual scripts
  data/              # local cache of downloaded candles (gitignored)
```

Most modules are still empty stubs — see Status below for what's actually built.

## Getting started

```bash
git clone https://github.com/withaphelion-afk/orbit.git
cd orbit
uv sync --extra dev
uv run pytest -q
```

That installs dependencies into a local `.venv` and confirms the test suite passes. Copy `.env.example` to `.env` and fill in secrets (e.g. Telegram bot token) only when you actually need them — nothing requires secrets yet.

## For contributors (including other Claude sessions)

Read in this order before starting work:

1. **This README** — what the project is, how it's laid out, and the full plan below.
2. **`git log`** — recent commits explain what's actually been built vs. planned.
3. **`src/orbit/core/types.py`** — the shared vocabulary (`Candle`, `Signal`, `TradeSuggestion`, `JournalEntry`, `Regime`) every module is built around.

Design principles to keep in mind while contributing:
- One strategy at a time — don't build a plugin system for hypothetical future strategies.
- Config lives in `config/settings.py`, not hardcoded in modules.
- Keep modules independently testable: pure functions where possible (`data/` returns candles, `features/` turns candles into signals, `strategy/` turns signals into trade suggestions).

This README is the single source of truth for planning — update it in place when a phase's status changes, instead of writing the plan elsewhere.

## Status

- `core/types.py` — shared data model (`Candle`, `Signal`, `TradeSuggestion`, `JournalEntry`, `Regime`, `EphemerisSnapshot`, `FeatureRecord`) — done.
- `data/binance.py` + `data/silver.py` — fetch BTC/ETH/SOL and silver daily candles from public APIs (no keys needed) — done. Run with `uv run python scripts/fetch_data.py`.
- `data/ephemeris.py` — daily planetary positions (zodiac sign + retrograde) via Skyfield, 60-year vectorized backfill — done. Run with `uv run python scripts/fetch_ephemeris.py`.
- `data/storage.py` — save/load candles and ephemeris snapshots as CSV under `data/` — done.
- `features/store.py` — the feature store: append-only CSV per asset, long format (date, name, value) — done.
- `features/technical.py` — daily return, close vs. 50/200-day SMA, 20-day volatility — done.
- `features/regime.py` — the regime gate (BTC+ETH 50/200-day SMA trend, both must agree for BULL/BEAR or it's CHOPPY) plus `compute_regime_series` to log its full history, not just a live reading — done.
- `features/astro.py` — encodes ephemeris sign/retrograde as numeric features per tracked asset — done.
- `scripts/compute_features.py` — runs the full pipeline (technical + regime + astro) into the feature store — done, verified against real data (BTC/ETH/SOL/silver, 60 years of ephemeris).
- Per-asset entry scoring, the actual strategy rules, backtesting, the journal, and the 24/7 runner — not started yet.

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
| Feedback loop | Trade journal of every suggestion + decision + outcome, used to periodically reweight the scorecard |

### Astro-transit research track

Treated as one testable input among others — back-tested with the same rigor as technical signals, not taken on faith.

- **Ephemeris source**: Skyfield (pure Python, no compiler needed) — exact planetary positions/transits for any date, free, precise. (Originally planned as Swiss Ephemeris via `pyswisseph`, but that needs a C++ compiler not available on this machine.)
- **Event tagging**: a table of historical transit events (sign changes, retrogrades, conjunctions/aspects) mapped to date ranges, joined against price history to compute frequency, average move and win rate after each event type.
- **Significance testing**: long-cycle transits (e.g. Jupiter ~12 years) give very few historical samples — explicitly test whether any correlation is statistically real or noise before trusting it.
- **Status**: ephemeris data pipeline built (60 years of daily positions for all 10 planets, verified against known real transit dates). Event tagging + price join not started yet.

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
| 2. Data pipeline | Price data + ephemeris data, stored locally | Done |
| 3. Backtest engine | Walk-forward validation; test astro factors for significance | Feature store built (technical + regime + astro); backtest engine itself not started |
| 4. Trade journal + scorecard | Logging schema for every signal and decision | Not started |
| 5. 24/7 runner | Always-on service, evaluates on schedule, logs/alerts, no execution | Not started |
| 6. Feedback loop | Review cadence to correct/reweight the scorecard | Not started |
| 7. Auto-execution | Enabled later, once confidence is earned | Not started |

### Open decisions

- **Project name**: working title **Orbit** (used for the astro-transit + always-on-monitoring theme).
- **Strategy definition**: exact assets/timeframe/entry-exit rules for the single strategy — not yet locked; deliberately deferred while the data layer gets built out first.
- **Hosting for the 24/7 runner**: VPS vs home server — not yet decided.
