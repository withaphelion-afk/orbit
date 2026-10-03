# Orbit web terminal

The React front end for Orbit: a keyboard-first trading terminal. It has
live prices, a watchlist, charts over the full stored history, strategy
suggestions to decide on, the journal, the backtest and feedback loop, the
Vedic playbook and model, and runner status.

Everything on screen is real. There is no mock data. When a report doesn't
exist yet (no backtest before the first analysis run, say), its screen says so
and how to produce it, instead of showing something made up.

Built with Vite, React 19 and TypeScript. It uses TradingView's embedded widget
and `lightweight-charts` for charts, TanStack Query for server state, zustand
for terminal state, and `cmdk` for the command palette.

## Run it

To just use it: `python scripts/start_orbit.py` from the repo root (see the
main README). It builds this app, and the API serves it at
http://127.0.0.1:8000.

To work on the UI, run the backend (`python scripts/start_orbit.py
--no-browser`, after the main README's Getting started data scripts), then:

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

### The cloud build (static, installable)

`VITE_ORBIT_STATIC=1 npm run build` builds the terminal with no server behind
it, as deployed to Vercel (`.github/workflows/deploy-web.yml`).
`src/api/static.ts` reads every API answer from the `site` branch of the
private data repo (`VITE_ORBIT_DATA_REPO`) through GitHub with the viewer's
token, and starts the `decide` / `analysis` workflows of `VITE_ORBIT_GITHUB_REPO`
for Take/Skip/Modify and RUN ANALYSIS. Live crypto prices come from Binance's
public mirror in the browser. The screens can't tell which client they have.

The app is installable (`public/manifest.webmanifest`, icons, and `public/sw.js`,
which caches only the app's own files, never data).

## Layout

```
src/
  api/          types.ts (mirrors the backend), http.ts (live API) / static.ts (cloud), hooks.ts (queries)
  state/        store.ts: view, active asset, live prices, toast, runCommand()
  hooks/        terminal keys, live price feed, clock
  lib/          command parser, formatting, indicators, decision validation
  components/   CommandBar, FunctionBar, Palette, Panel, NotBuilt / QueryState
  panels/       one file per function; astro/ holds the playbook views
  styles/       tokens.css (colours, fonts) and app.css
  config.ts     assets, price decimals, TradingView symbols
```

A panel loads the first time its function is opened (its code is a separate
chunk) and then stays mounted, only hidden when you switch functions. That way
the live chart never reloads and a half-typed note survives. Orbit's own chart
library loads only in ORBIT chart mode.

## Screens

| Code | Key | What it shows | Data |
|---|---|---|---|
| MON | F2 | Chart and watchlist, plus the regime gate and next transit | quotes, regime, sky |
| GP | F3 | **LIVE**: TradingView's chart (their data) with its RSI(14) study. **ORBIT**: Orbit's live divergence chart at 1H/4H/1D/1W. Binance bars stream in real time (silver: Orbit's bars, hourly). It has an RSI pane with 70/30 bands, and every divergence the shared algorithm finds: solid once confirmed, dashed while forming, scored, with ✓/✗ and "mark one it missed". | Binance, bars, divergences, divergence model |
| ALRT | F9 | Divergence alerts on every timeframe (runner + live chart), badge on the navigation, ✓/✗ to teach the model | alerts, divergence model |
| SUGG | F4 | RSI divergence suggestions: levels, the signals behind each, confidence; take / skip / modify (J/K, T/S/M) | suggestions |
| JRNL | F5 | Every decision and its outcome, expired suggestions, and what skipped ones would have returned | journal |
| DRIFT | F6 | Three views:<br>**DRIFT**: live vs backtest win rate (z-score) and the cumulative-R curve against the backtest's expectation<br>**BACKTEST**: per-asset results over the full history, long vs short, exits, the equity curve, by year<br>**FEEDBACK**: what the divergence model learned, its walk-forward check, and whether it's trusted yet. DRIFT and BACKTEST switch between 1D and 4H | drift, backtest, calibration |
| ASTRO | F7 | Six tabs, all Vedic (sidereal, Lahiri):<br>**PROJECTIONS** (default): each upcoming event per asset, with what history says followed it. It shows the odds vs normal with their range, size, timing and reliability (N, q, label), and nothing below STRONG/MODERATE is shown as trusted. Each row opens its evidence, plus a forward track record.<br>**SKY**: the 9 grahas now: rashi, degree, nakshatra and pada, vakri / asta / uchcha / neecha, next change<br>**EVENTS**: past and upcoming events (ingresses, stations, yuti, drishti, asta, yuddha, lunations, grahan, yogas), with exact times<br>**PLAYBOOK**: the RUN ANALYSIS button, per-asset patterns (daily and hourly labels), and every occurrence with exception context and move timing. Click an occurrence for its hourly chart around the exact moment.<br>**CHOP**: Vedic states vs sideways markets<br>**MODEL**: does the whole Vedic sky improve a price-only forecast? Walk-forward, against shifted controls | sky, transits, playbook, analysis runs, intraday, model |
| SYS | F8 | Runner heartbeat, the run button with run history and schedule, which layers are built, feed provenance, runner log, settings | system, analysis runs |
| HELP | F1 | Commands and keys | — |

In the ORBIT chart, Vedic markers are limited to every vakri / margi station
and eclipse, the slow grahas' rashi changes (Guru, Shani, Rahu), and anything
the playbook rates for that asset (drawn as circles). Everything else would
add hundreds of markers a year.

## API contract

All shapes are in [`src/api/types.ts`](src/api/types.ts). They mirror
`src/orbit/core/types.py` and `src/orbit/api/schemas.py` field for field
(snake_case, ISO-8601 UTC). Change them together.

| Method | Path | Returns |
|---|---|---|
| GET | `/api/quotes` | `Quote[]`: last price (live, delayed or last stored), previous close, day range, 30-day sparkline, regime and its scope |
| GET | `/api/candles/{asset}` | `Candle[]`: the full stored history, each bar tagged with its venue |
| GET | `/api/signals/{asset}` | `Signal[]`: every RSI divergence (dated to its confirmation bar), and the days the regime turned BULL or BEAR |
| GET | `/api/regime` | `RegimeReading[]`: the shared BTC/ETH gate and silver's own trend, with the history of changes |
| GET | `/api/sky` | `SkyPosition[]`: the 9 grahas now (sidereal): rashi, degree, nakshatra, pada, vakri, asta, dignity, next change |
| GET | `/api/transits?from&to&include_moon` | `TransitView[]`: Vedic events in the window (default: 90 days back to 180 ahead; Moon-driven events only with `include_moon`), each with the assets whose playbook rates it |
| GET | `/api/playbook` | `PlaybookOverview`: run metadata, tests per family, placebo check |
| GET | `/api/playbook/{asset}` | `PlaybookView`: patterns (without occurrences) and chop states |
| GET | `/api/playbook/{asset}/patterns/{id}` | `PatternResult`: every occurrence with its outcome and context |
| GET | `/api/system` | `SystemStatus`: runner, components, feeds, log, config |
| POST | `/api/analysis/runs` | Start an analysis run: `{ placebo, refresh }` → `202 AnalysisRun`, or `409` if one is already going |
| GET | `/api/analysis/runs`, `/api/analysis/runs/current`, `/api/analysis/runs/{id}` | Run history, the active run (progress, step, log), one run |
| GET | `/api/analysis/schedule` | `ScheduleView`: the daily time, the placebo day, the next scheduled run |
| GET | `/api/intraday/{asset}?at&before_hours&after_hours` | `Candle[]`: hourly bars around a moment (the drill-down chart) |
| GET | `/api/suggestions` | `SuggestionView[]`: suggestions waiting for a decision, newest first |
| POST | `/api/suggestions/{id}/decision` | Log `DecisionRequest` (`TAKEN` / `SKIPPED` / `MODIFIED` with levels) → `JournalRow`. `404` unknown, `409` already decided or expired, `422` MODIFIED without levels. Never places an order |
| GET | `/api/journal` | `JournalRow[]`: decided and expired suggestions with outcomes and counterfactuals, newest first |
| GET | `/api/drift?timeframe=1d\|4h` | `DriftReport`: live vs backtest for one timeframe; `404` before the first backtest |
| GET | `/api/bars/{asset}?timeframe=1h\|4h\|1d\|1w` | `BarRow[]`: the last 1,000 completed bars as `[time, open, high, low, close, volume]` |
| GET | `/api/divergences/{asset}` | `DivergenceSet`: recent divergence candidates per timeframe, scored, with outcomes and your labels |
| GET | `/api/divergences/model` | `DivergenceModel`: the weights the browser scores live divergences with, thresholds, trust |
| GET | `/api/alerts` | `AlertItem[]`: confirmed divergences above their timeframe's threshold, newest first |
| POST | `/api/divergences/label` | `DivergenceLabelRequest` (✓ real / ✗ not real, or a missed one): saved for the next retrain |
| GET | `/api/projections`, `/api/projections/track` | `ProjectionView[]` (upcoming events with their evidence) and the forward track record |
| GET | `/api/backtest`, `/api/backtest/{asset}` | `BacktestReport`: pooled and per-asset results; one asset's with every trade |
| GET | `/api/calibration` | `CalibrationReport`: the feedback loop's weights, out-of-sample check, and whether it sets confidence |
| GET | `/api/model/{asset}` | `ModelReport`: the Vedic model's walk-forward results, verdicts, controls and today's forecast |
| WS | `/ws` | `{"type":"tick","asset":"BTC","price":…,"timestamp":…,"source":"LIVE"}`. Silver's source is `DELAYED` |

## Keys

| Key | Action |
|---|---|
| `F1`–`F8` | HELP, MON, GP, SUGG, JRNL, DRIFT, ASTRO, SYS |
| `Ctrl/⌘ K` | Command palette |
| `/` or any letter | Type into the command line (`SOL GP`, `XAG ASTRO`, `SYS`…). Tab completes, ↑/↓ recall history |
| `1`–`4` | Switch asset |
| `Esc` | Close or blur, then back to MON |
