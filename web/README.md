# Orbit web terminal

The React front end for Orbit: a keyboard-first trading terminal that shows
the watchlist, a live chart, the suggestion queue, the journal, backtest-vs-live
drift, the astro research calendar and runner status.

Built with Vite, React 19 and TypeScript. It uses TradingView's embedded
widget and `lightweight-charts` for charts, TanStack Query for server state,
zustand for terminal state and `cmdk` for the command palette.

## Run it

```bash
cd web
npm install
npm run dev        # http://localhost:5173
```

It runs fully on built-in mock data until the backend is ready. The
**MOCK DATA** badge in the top bar tells you when that's the case.

| Script | What it does |
|---|---|
| `npm run dev` | Dev server with hot reload |
| `npm run build` | Typecheck, then production build to `dist/` |
| `npm test` | Unit tests (Vitest) |
| `npm run typecheck` | `tsc -b` only |
| `npm run lint` | oxlint |

## Layout

```
src/
  api/          types.ts (the contract), mock.ts, http.ts, hooks.ts; index.ts picks the source
  state/        store.ts: view, active asset, live prices, toast, runCommand()
  hooks/        terminal keys, live tick feed, clock
  lib/          command parser, formatting, indicators, decision validation
  components/   CommandBar, FunctionBar, Palette, Panel, small bits
  panels/       one file per function: Chart, Watchlist, Suggestions, Journal, Drift, Astro, System, Help
  styles/       tokens.css (colours, fonts) and app.css
  config.ts     assets, price decimals, TradingView symbols
```

Every panel stays mounted and is only hidden when you switch functions. That
way the live chart never reloads and a half-written decision note survives a
trip to another screen.

## Charts

The GP panel has two modes, toggled in its header (or `CHART LIVE` /
`CHART ORBIT` in the palette):

- **LIVE**: TradingView's
  [Advanced Chart widget](https://www.tradingview.com/widget-docs/widgets/charts/advanced-chart/),
  with live market data streamed by TradingView, their intervals and their
  drawing tools. It runs in an iframe, so Orbit can't draw on it. Symbols are
  set in `src/config.ts` (`BINANCE:BTCUSDT`, `BINANCE:ETHUSDT`,
  `BINANCE:SOLUSDT`, `OANDA:XAGUSD`). Keep the "chart by TradingView" credit
  link; the widget's terms require it.
- **ORBIT**: TradingView's open-source `lightweight-charts`, drawing Orbit's
  own candles with its signals, astro transits, 20D/50D averages and the
  pending suggestion's entry/stop/target lines. The last bar follows live
  ticks.

TradingView doesn't offer a public market-data API, so the watchlist,
suggestions and ORBIT chart get their prices from Orbit's own backend.

## Connecting the backend

Create `web/.env.local`:

```bash
VITE_ORBIT_API=http
ORBIT_API_TARGET=http://127.0.0.1:8000   # where the Orbit API runs
```

The dev server proxies `/api` and `/ws` to `ORBIT_API_TARGET`, so there's no
CORS to set up. For a deployed build, serve the API on the same origin, or
set `VITE_ORBIT_API_BASE=https://api.example` and allow that origin.

### API contract

All shapes are defined in [`src/api/types.ts`](src/api/types.ts).

- The core shapes (`Candle`, `Signal`, `TradeSuggestion`, `JournalEntry`)
  mirror `src/orbit/core/types.py` field for field, so pydantic's
  `model_dump(mode="json")` output fits directly.
- Timestamps are ISO-8601 UTC strings.
- `Asset` is `BTC | ETH | SOL | SILVER`. `Regime` (`BULL | BEAR | CHOPPY`) and
  `Planet` use the same enum values as `core/types.py`.

| Method | Path | Returns | Notes |
|---|---|---|---|
| GET | `/api/quotes` | `Quote[]` | One per tracked asset: last price, previous close, day high/low, about 30 daily closes for the sparkline, regime tag, `LIVE`/`MOCK` source |
| GET | `/api/candles/{asset}` | `Candle[]` | Daily bars, oldest first. About 240 is plenty |
| GET | `/api/signals/{asset}` | `Signal[]` | Historical signals to mark on the ORBIT chart |
| GET | `/api/suggestions` | `SuggestionView[]` | Pending only: `{ id, created_at, risk_reward, suggestion }` |
| POST | `/api/suggestions/{id}/decision` | `JournalRow` | Body is a `DecisionRequest`: `{ decision, notes, entry_price?, stop_loss?, take_profit? }`. The price overrides only matter for `MODIFIED`. Remove the suggestion from pending. Return 404 or 409 if it's gone |
| GET | `/api/journal` | `JournalRow[]` | Newest first: `{ id, decided_at, entry: JournalEntry, counterfactual_pnl }` |
| GET | `/api/drift` | `DriftReport` | Backtest vs live: win rate, avg R, max drawdown, z-score, status, 1σ band, equity curve |
| GET | `/api/astro` | `AstroEvent[]` | Transit calendar, past and upcoming |
| GET | `/api/system` | `SystemStatus` | Runner state, strategy, last/next evaluation, feeds, alert log, read-only config |
| WS | `/ws` | messages | `{"type":"tick","asset":"BTC","price":64210.5,"timestamp":"..."}` |

Two fields go beyond the core types and need agreeing with the backend:

- **`outcome_pnl`** is read as a percent return on the position (`2.4` means +2.4%).
- **`counterfactual_pnl`** on a journal row is what a *skipped* suggestion
  would have returned. It powers the journal's "skipped would-be" figure.
  Send `null` until it's known.

## Keys

| Key | Action |
|---|---|
| `F1`–`F8` | HELP, MON, GP, SUGG, JRNL, DRIFT, ASTRO, SYS |
| `Ctrl/⌘ K` | Command palette |
| `/` or any letter | Type into the command line (`SOL GP`, `XAG DRIFT`, `SUGG`…). Tab completes, ↑/↓ recall history |
| `1`–`4` | Switch asset |
| `J` / `K` | Next / previous suggestion (SUGG) |
| `T` `S` `M` | Take, skip or modify the selected suggestion; `Ctrl ↵` logs it |
| `Esc` | Cancel or close, then back to MON |
