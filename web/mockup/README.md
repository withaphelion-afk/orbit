# Orbit terminal mockup

A single-file, clickable mockup of the planned web UI. It exists to lock the
look and the interaction model. The real app is the React project in `web/`
(see `web/README.md`); keep this file as the visual reference.
Open `index.html` in a browser. It needs no server and no build step.

Everything on screen is generated sample data, seeded so it looks the same on
every load. Nothing talks to the backend yet.

## What it shows

| Code  | Key | Screen |
|-------|-----|--------|
| HELP  | F1  | Commands and keyboard reference |
| MON   | F2  | Chart with the watchlist on the right (queue and drift status at its foot) |
| GP    | F3  | Candlestick chart with signal markers, astro transits, pending entry/stop/target |
| SUGG  | F4  | Suggestion queue: confidence, reward:risk, signal breakdown, Take / Skip / Modify |
| JRNL  | F5  | Journal with filters, sorting, and "would-be" P&L on skipped trades |
| DRIFT | F6  | Backtest-expected vs live equity, win-rate z-score |
| ASTRO | F7  | Transit calendar (research track, placeholder dates) |
| SYS   | F8  | Runner, feeds, alert log, read-only config |

Type commands like `SOL GP`, `BTC`, `SUGG` in the top command line. `Ctrl+K`
opens the palette; `1`-`4` switch asset; `J`/`K`, `T`/`S`/`M` drive the queue.

## How it maps to the backend

The mockup's data mirrors `src/orbit/core/types.py`: suggestions are
`TradeSuggestion` + `Signal[]`, and taking/skipping/modifying one produces a
`JournalEntry` with a `Decision`. The only additions the UI needs from an API
are ids on suggestions and journal rows, and derived fields such as
reward:risk and the drift report.
