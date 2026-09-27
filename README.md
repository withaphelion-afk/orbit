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
  web/               # React trading terminal (see web/README.md)
  tests/             # mirrors src/orbit structure
  scripts/           # one-off manual scripts
  data/              # local cache of downloaded candles (gitignored)
```

Most modules are still empty stubs — see Status below for what's actually built.

## Where to learn more (context for contributors, including other Claude sessions)

Before doing any work here, read these in order:

1. **This README** — what the project is and how it's laid out.
2. **The shared project doc** — architecture, build phases, the astro-transit research track, and open decisions: [Orbit — Systematic Trading Strategy](https://claude.ai/code/artifact/d1aae7ea-a032-4196-992d-705ff5b70a37). This is the single source of truth for planning — check it before starting work and update it when a phase's status changes, instead of creating a new doc.
3. **`git log`** — recent commits explain what's actually been built vs. planned.
4. **`src/orbit/core/types.py`** — the shared vocabulary (`Candle`, `Signal`, `TradeSuggestion`, `JournalEntry`) every module is built around.

## Getting started

```bash
git clone https://github.com/withaphelion-afk/orbit.git
cd orbit
uv sync --extra dev
uv run pytest -q
```

That installs dependencies into a local `.venv` and confirms the test suite passes. Copy `.env.example` to `.env` and fill in secrets (e.g. Telegram bot token) only when you actually need them — nothing requires secrets yet.

The web terminal lives in `web/` and runs on mock data until the API is ready:

```bash
cd web && npm install && npm run dev
```

See [`web/README.md`](web/README.md) for the screens and the API contract it expects from the backend.

Design principles to keep in mind while contributing (see the doc for the full reasoning):
- One strategy at a time — don't build a plugin system for hypothetical future strategies.
- Config lives in `config/settings.py`, not hardcoded in modules.
- Keep modules independently testable: pure functions where possible (`data/` returns candles, `features/` turns candles into signals, `strategy/` turns signals into trade suggestions).

## Status

Just getting started — see the doc's Build Plan section for current phase status.
