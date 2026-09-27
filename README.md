# Orbit — Systematic Trading Strategy

A 24/7 systematic trading assistant for **BTC, ETH, SOL, and Silver**. It watches markets continuously and suggests trades with a stated confidence level — it does not place trades on its own (yet). The plan is to earn trust in the system over time before ever turning on auto-execution.

This project doubles as a learning project. Every module is built to be understandable, not just functional — comments and docs explain *why*, not just *what*.

## Core ideas

- **One strategy at a time** — no juggling multiple competing strategies until one is proven.
- **Your experience becomes rules** — trading intuition gets written down as explicit, testable logic instead of staying a "feeling."
- **Self-correcting** — the system tracks its own live performance against what backtesting predicted, and flags itself (or scales down) when reality drifts from expectation.
- **Suggestions, not autopilot** — every trade idea comes with its reasoning, for you to approve, until auto-execution is explicitly turned on later.

## Project layout (planned)

```
orbit/
  data/          # scripts to fetch and store price + ephemeris data
  features/      # turning raw price data into signals (indicators, regimes, astro transits)
  strategy/      # the one active strategy's entry/exit/risk rules
  backtest/      # tests the strategy against historical data before it ever goes live
  journal/       # logs every suggestion, your decision, and the outcome
  runner/        # the 24/7 process that ties it all together and sends alerts
```

Nothing above exists yet — we're building it piece by piece, starting with the data layer.

## Where to learn more

The full plan — architecture, build phases, the astro-transit research track, open decisions — lives in the shared project doc: [Orbit — Systematic Trading Strategy](https://claude.ai/code/artifact/d1aae7ea-a032-4196-992d-705ff5b70a37)

## Status

Just getting started — see the doc's Build Plan section for current phase status.
