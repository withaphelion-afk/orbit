# Orbit web terminal

The React front end for Orbit: a keyboard-first trading terminal. It has
live prices, a watchlist, charts over the full stored history, the transit
playbook, runner status, and screens for the layers still to come
(suggestions, journal, drift).

Everything on screen is real. There is no mock data. When a backend layer
doesn't exist yet, its screen says so instead of showing something made up.

Built with Vite, React 19 and TypeScript. It uses TradingView's embedded widget
and `lightweight-charts` for charts, TanStack Query for server state, zustand
for terminal state, and `cmdk` for the command palette.

## Run it

The terminal reads everything from the Orbit API, so start the backend
first. From the repo root:

```bash
uv sync --extra dev
uv run python scripts/fetch_data.py        # first run builds full price history (~30s)
uv run python scripts/fetch_ephemeris.py   # 60 years back, 2 ahead
uv run python scripts/build_playbook.py    # transit playbook (~25s)
uv run python -m orbit.api                 # API on http://127.0.0.1:8000
uv run python -m orbit.runner.loop         # optional: keeps data fresh every hour
```

Then the web app:

```bash
cd web
npm install
npm run dev        # http://localhost:5173, proxies /api and /ws to the API
```

If the API isn't running, the top bar shows **API OFFLINE**, and every screen
shows the command that starts it.

| Script | What it does |
|---|---|
| `npm run dev` | Dev server with hot reload |
| `npm run build` | Typecheck, then production build to `dist/` |
| `npm test` | Unit tests (Vitest) |
| `npm run typecheck` | `tsc -b` only |
| `npm run lint` | oxlint |

Set `ORBIT_API_TARGET` in `web/.env.local` if the API runs somewhere other
than `127.0.0.1:8000`. For a production build served from a different origin,
set `VITE_ORBIT_API_BASE`.

## Layout

```
src/
  api/          types.ts (mirrors the backend), http.ts (client), hooks.ts (queries)
  state/        store.ts: view, active asset, live prices, toast, runCommand()
  hooks/        terminal keys, live price feed, clock
  lib/          command parser, formatting, indicators, decision validation
  components/   CommandBar, FunctionBar, Palette, Panel, NotBuilt / QueryState
  panels/       one file per function; astro/ holds the playbook views
  styles/       tokens.css (colours, fonts) and app.css
  config.ts     assets, price decimals, TradingView symbols
```

Panels stay mounted and are only hidden when you switch functions. That way
the live chart never reloads.

## Screens

| Code | Key | What it shows | Data |
|---|---|---|---|
| MON | F2 | Chart and watchlist, plus the regime gate and next transit | quotes, regime, sky |
| GP | F3 | **LIVE**: TradingView's chart (their data). **ORBIT**: the full stored history with regime flips and transit markers | candles, signals, transits |
| SUGG | F4 | Suggestion queue (take/skip/modify) | *strategy not built* |
| JRNL | F5 | Journal of decisions and outcomes | *journal not built* |
| DRIFT | F6 | Backtest vs live | *backtest not built* |
| ASTRO | F7 | Four tabs. **SKY**: current positions. **EVENTS**: past and upcoming transits. **PLAYBOOK**: per-asset patterns and every occurrence with exception context. **CHOP**: transit states vs sideways markets | sky, transits, playbook |
| SYS | F8 | Runner heartbeat, which layers are built, feed provenance, runner log, settings | system |
| HELP | F1 | Commands and keys | — |

The SUGG, JRNL and DRIFT screens are fully built. They read
`/api/system → components` and switch on as soon as the backend reports that
layer as built.

In the ORBIT chart, transit markers are limited to every station,
slow-planet ingresses, and anything the playbook rates for that asset (drawn
as circles). Fast ingresses alone would add ~40 markers a year.

## API contract

All shapes are in [`src/api/types.ts`](src/api/types.ts). They mirror
`src/orbit/core/types.py` and `src/orbit/api/schemas.py` field for field
(snake_case, ISO-8601 UTC). Change them together.

| Method | Path | Returns |
|---|---|---|
| GET | `/api/quotes` | `Quote[]`: last price (live, delayed or last stored), previous close, day range, 30-day sparkline, regime and its scope |
| GET | `/api/candles/{asset}` | `Candle[]`: the full stored history, each bar tagged with its venue |
| GET | `/api/signals/{asset}` | `Signal[]`: the days the regime reading turned BULL or BEAR |
| GET | `/api/regime` | `RegimeReading[]`: the shared BTC/ETH gate and silver's own trend, with the history of changes |
| GET | `/api/sky` | `SkyPosition[]`: today's position of each body and its next transit |
| GET | `/api/transits?from&to` | `TransitView[]`: events in the window (default: 90 days back to 180 ahead), each with the assets whose playbook rates it |
| GET | `/api/playbook` | `PlaybookOverview`: run metadata, tests per family, placebo check |
| GET | `/api/playbook/{asset}` | `PlaybookView`: patterns (without occurrences) and chop states |
| GET | `/api/playbook/{asset}/patterns/{id}` | `PatternResult`: every occurrence with its outcome and context |
| GET | `/api/system` | `SystemStatus`: runner, components, feeds, log, config |
| GET | `/api/suggestions`, `/api/journal` | `[]` until those layers exist |
| POST | `/api/suggestions/{id}/decision` | `501` until the strategy layer exists |
| GET | `/api/drift` | `404` until the backtest layer exists |
| WS | `/ws` | `{"type":"tick","asset":"BTC","price":…,"timestamp":…,"source":"LIVE"}`. Silver's source is `DELAYED` |

## Keys

| Key | Action |
|---|---|
| `F1`–`F8` | HELP, MON, GP, SUGG, JRNL, DRIFT, ASTRO, SYS |
| `Ctrl/⌘ K` | Command palette |
| `/` or any letter | Type into the command line (`SOL GP`, `XAG ASTRO`, `SYS`…). Tab completes, ↑/↓ recall history |
| `1`–`4` | Switch asset |
| `Esc` | Close or blur, then back to MON |
