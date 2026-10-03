# Orbit — Systematic Trading Strategy

A 24/7 systematic trading assistant for **BTC, ETH, SOL, and Silver**. It watches markets continuously and suggests trades with a stated confidence level — it does not place trades on its own (yet). The plan is to earn trust in the system over time before ever turning on auto-execution.

This project doubles as a learning project. Every module is built to be understandable, not just functional — comments and docs explain *why*, not just *what*.

**It runs in the cloud for free, with no PC on:** GitHub Actions runs the runner and the analysis, and a Hugging Face Space serves the web terminal. See [Free cloud hosting](#free-cloud-hosting-no-pc-needed). **To run it on your own machine instead (Windows, macOS, Linux), see [Install and run on any machine](#install-and-run-on-any-machine).**

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
    vedic/         # Vedic (Jyotish) rules: sidereal sky, grahas, events, drishti, yogas, states
    analysis/      # research: outcomes, significance, the playbook, the Vedic model
    api/           # HTTP + WebSocket API the web terminal reads
    strategy/       # the one active strategy (RSI divergence), live suggestions, the feedback loop
    backtest/       # full-history backtest + live-vs-backtest drift
    journal/        # every suggestion, your decision, and its outcome
    runner/          # 24/7 loop: data -> features -> suggestions; daily analysis
    alerts/          # Telegram/console notifier (not built yet)
    launcher.py      # start/stop/status/autostart on any OS (scripts/start_orbit.py)
    cloud.py         # the web server on a free cloud host (Hugging Face Space)
    datasync.py      # shares the data (prices, caches, journal) through the data repo
    outputs.py       # shares the computed results the same way
    config/          # settings (assets, timeframe, secrets via .env)
    core/            # shared types used everywhere (Candle, Signal, Trade, ...)
  web/               # React trading terminal (see web/README.md)
  deploy/hf-space/   # the Hugging Face Space: Dockerfile and its README
  .github/           # CI, deployment, and the hourly runner / daily analysis jobs
    src/api/         # API client; types mirrored from core/types.py and api/schemas.py
    src/panels/      # one screen per terminal function (chart, watchlist, suggestions, ...)
  tests/             # mirrors src/orbit structure
  scripts/           # start/stop/autostart, plus one-off manual scripts
  data/              # everything local to this machine: prices, ephemeris, playbook, journal (gitignored)
```

Only `alerts/` is still an empty stub — see Status below for what's built.

## Install and run on any machine

### 1. Install three tools (once)

| Tool | Why | Get it |
| --- | --- | --- |
| git | To clone Orbit and share data through GitHub | [git-scm.com](https://git-scm.com/downloads). Log in to GitHub once (for example `gh auth login`) so this machine can also send its data. |
| uv | Installs Python 3.11+ and every package Orbit needs | [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) |
| Node.js 20.19+ | Builds the web terminal | [nodejs.org](https://nodejs.org) |

### 2. Get Orbit and start it

```bash
git clone https://github.com/withaphelion-afk/orbit.git
cd orbit
uv run python scripts/start_orbit.py
```

Or double-click `start_orbit.cmd` on Windows, or run `./start_orbit.sh` on macOS/Linux. No API keys or accounts are needed.

### 3. What happens the first time

1. It creates the Python environment (`.venv`) and builds the web terminal: a few minutes.
2. It downloads the shared data from GitHub: price histories, the silver history and NASA's ephemeris (about 26 MB). Nothing has to be re-downloaded from the exchanges.
3. It starts the API and the 24/7 runner in the background and opens http://127.0.0.1:8000.
4. The runner's first cycle fetches the latest prices and builds the Vedic sky and features: a few minutes.
5. The first analysis run builds the playbook, backtest, feedback loop and model: about 15–20 minutes. Until it finishes, those screens say they haven't been generated yet.

After that the runner keeps everything current by itself: prices every hour, the analysis daily at 00:30 UTC, and a data sync with GitHub once a day.

### 4. Every day

| To | Run |
| --- | --- |
| Start Orbit | `uv run python scripts/start_orbit.py` (safe to run when it's already running) |
| Check it | `uv run python scripts/start_orbit.py --status` |
| Stop it | `uv run python scripts/stop_orbit.py` |
| Start it at login | `uv run python scripts/autostart.py` (`--remove` to undo) |
| Update to the latest code | `git pull`, then stop and start |

### If something doesn't work

| What you see | What to do |
| --- | --- |
| `No .venv yet. Install uv` | Install uv (step 1) and run the start command again. |
| `Node.js/npm not found` | Install Node.js 20.19+. Everything else runs meanwhile, just without the web terminal. |
| `--status` says the runner is running, but SYS (F8) shows it NEVER_RUN or STALE | A leftover file points at another program. Stop Orbit, delete `data/runner_status.json` and the `data/run` folder, and start again. |
| The runner log shows price errors from Binance (HTTP 451 or 403) | Orbit uses Binance's market-data mirror (`data-api.binance.vision`), which works from the US too. If a region still blocks it, this machine gets every price from GitHub through the sync. `uv run python scripts/probe_sources.py` shows which sources answer. |
| `Data sync: ... Couldn't send this machine's data` | This machine can read from GitHub but not write to it (not logged in, or no access). It still receives everything. Log in to GitHub to send too. |
| Port 8000 is already in use | Put `ORBIT_API_PORT=8001` (or any free port) in a `.env` file in the orbit folder. |
| Windows blocks Python packages (Smart App Control) | Orbit avoids the affected packages. If a start still fails, send the error. |

Logs are in `data/logs/` (`api.out`, `runner.out`, `silver.out`, `runner.log`). When asking for help, send the output of `uv run python scripts/start_orbit.py --status` and the last lines of `data/logs/runner.out`.

### For developers

```bash
uv sync --extra dev
uv run pytest -q          # the tests never touch GitHub (tests/conftest.py)
cd web && npm install && npm run dev   # the web terminal with hot reload, on http://localhost:5173
```

Copy `.env.example` to `.env` for settings (none are required). The data scripts can still be run by hand, though `start_orbit` and the runner make them unnecessary:

```bash
uv run python scripts/fetch_data.py        # full daily + hourly history (~8 min from scratch; the shared data makes it quick)
uv run python scripts/fetch_ephemeris.py   # the Vedic sky 2000-2028 and its ~33,000 events (~30 s)
uv run python scripts/compute_features.py  # technical, regime and Vedic features
uv run python scripts/build_playbook.py    # Vedic playbook, daily + hourly (~5 min); or press RUN ANALYSIS in the web terminal
uv run python scripts/placebo_check.py     # sanity check of the playbook method (~40 min)
uv run python scripts/backfill_silver.py   # the spot-silver download (already shared on GitHub; only needed without it)
```

**Note for Windows machines with Smart App Control / Application Control:** it blocks pandas' compiled files, so nothing in `src/` imports pandas; the maths uses numpy, which loads fine. The launcher uses only the standard library for the same reason.

### Running Orbit on your machine

Without the cloud setup below, Orbit runs on whichever PC is on. Each machine keeps its own `data/`, and the part that is slow or impossible to rebuild is shared through GitHub (see [Shared data](#shared-data-the-github-data-branch) below), so a new machine starts with the full histories instead of downloading them again.

| Command | What it does |
| --- | --- |
| `python scripts/start_orbit.py` | Starts the API (which serves the web terminal, rebuilt first if its sources changed), the runner, and the silver download if it isn't complete, each detached in the background; opens http://127.0.0.1:8000. Safe to run twice. |
| `python scripts/start_orbit.py --status` | What's running, whether the web build and silver download are done, whether autostart is on |
| `python scripts/stop_orbit.py` | Stops the API, runner and silver download. An analysis run in progress finishes on its own. |
| `python scripts/autostart.py` | Start Orbit at login (per user, no admin): a `.cmd` in the Windows Startup folder, a macOS LaunchAgent, or a Linux XDG autostart entry. `--remove` undoes it. |
| `python scripts/sync_data.py` | Syncs the shared data with GitHub now (`--pull` to only take, `--status` to see the last sync). start_orbit and the runner do this on their own. |

Double-click shortcuts: `start_orbit.cmd` on Windows, `./start_orbit.sh` on macOS/Linux. Output goes to `data/logs/{api,runner,silver}.out`; the runner's own log is `data/logs/runner.log`. Use the `.venv` Python (`.venv/Scripts/python` on Windows, `.venv/bin/python` elsewhere) or `uv run python` for the commands above; the launcher itself works with any Python 3.11+.

### Shared data: the GitHub `data` branch

Everything Orbit needs that can't be rebuilt in a few seconds lives on a separate `data` branch of this repo, next to the code but never mixed into it:

| Shared on GitHub | Why |
| --- | --- |
| `{BTC,ETH,SOL,SILVER}_{1d,1h}.csv` and `history_report.json` | The stitched price histories. Rebuilding takes minutes, and some venues are blocked in some regions. |
| `cache/dukascopy/**` | The spot-silver files, 2003 on. Downloading them takes hours because the feed throttles hard. |
| `ephemeris_cache/de421.bsp` | NASA JPL's ephemeris kernel, so the Vedic sky can be computed offline. |
| `analysis/placebo.json` | The latest placebo check (about 40 minutes to rerun). |
| `journal/suggestions.json` | Your decisions and notes, **only if you turn it on** (below). |

Everything else (features, the Vedic sky and events, the playbook, the backtest, the feedback loop, the model) is rebuilt on each machine by its runner and its first analysis run, from the shared data.

**When it syncs:**
- `start_orbit` syncs before starting anything, so a fresh clone gets the data first.
- The runner then syncs once a day.
- `python scripts/sync_data.py` syncs on demand.

**How a sync works:**
- It fetches the branch and merges it file by file with `data/`, writes each winner to both sides, and pushes what this machine has that GitHub doesn't.
- If another machine pushed in the meantime, it fetches and merges again.
- Files are merged by rules, never by git, so there are no merge conflicts:
  - Price histories: the better file wins. For silver, spot beats futures; then the longer history; then the later last bar. On a tie GitHub's copy stays, so to publish a deliberate rebuild of a history, run `python scripts/sync_data.py --prefer-local`.
  - Silver cache and kernel: files are only ever added.
  - Placebo: the newer check wins.
  - Journal: records are joined by suggestion, and a decision beats an undecided one. If both machines decided, the first decision stands and the other one (decision, time and notes) is written into its notes. The local journal is backed up (`data/journal/backups/before-sync-*.json`) before a sync changes it.
- The branch is checked out in `.orbit-sync/` (ignored by the main branch), and nothing is ever deleted.
- Pushing needs the machine's normal GitHub login. A machine that can only read still gets everything; it reports the failed push once and tries again a day later. Nothing ever waits for a password prompt.
- Tests never sync: `tests/conftest.py` turns the sync off for every test, and CI sets `ORBIT_DATA_SYNC=0`.

**Taking the data down.** Delete the `data` branch on GitHub, and put `ORBIT_DATA_SYNC=0` in `.env` on every machine. A machine that synced before refuses to put a deleted branch back, even with the setting still on. To publish again later, run `python scripts/sync_data.py --recreate` on one machine. That starts a new, empty history from its current data, so nothing old comes back.

**The journal is shared only through a private repo.** The data branch can live in another repo: point `ORBIT_DATA_SYNC_REMOTE` at a git remote for it (the cloud setup uses the private `orbit-data`, as remote `data`). With a private remote, `ORBIT_DATA_SYNC_JOURNAL=1` shares the journal too. Never turn that on against a public repo. `ORBIT_DATA_SYNC=0` turns the sync off entirely.

### Web terminal

The UI is a separate React app in `web/`, and it needs Node 20.19+ or 22.12+. It reads everything from the API above, so start that first:

```bash
cd web
npm install
npm run dev      # http://localhost:5173
npm test         # unit tests
```

It opens on the monitor screen: a chart on the left and the watchlist on the right. Press `F1` for every command and key.

- **Everything shown is real:** live prices from Binance (silver delayed, from Yahoo), the stored histories, the regime gate, the Vedic sky, the playbook, suggestions, the journal, the backtest and runner status. There is no mock data.
- **Chart:** LIVE mode is TradingView's embedded chart with their own data. ORBIT mode draws the full stored history with every RSI divergence, regime flips and Vedic markers.
- **Reports not generated yet** (a backtest before the first analysis run, say) show an explicit empty screen saying how to produce them.

`start_orbit.py` builds and serves the web terminal from the API, so `npm run dev` is only needed while working on the UI.

See [`web/README.md`](web/README.md) for the screens and the API contract.

## Free cloud hosting (no PC needed)

Everything runs on free services, and no machine has to stay on:

| Where | What | When |
| --- | --- | --- |
| GitHub Actions, `runner` workflow | One runner cycle: new bars, features, suggestions created, expired and resolved | Every hour |
| GitHub Actions, `analysis` workflow | Playbook, backtest, feedback loop and Vedic model; placebo check on Sundays | Daily 00:30 UTC, and from the RUN ANALYSIS button |
| Private repo `orbit-data` | `data` branch: prices, silver cache, kernel, journal (the [data sync](#shared-data-the-github-data-branch)). `outputs` branch: the latest computed results (`src/orbit/outputs.py`) | Written by every job and by the Space |
| Hugging Face Space (Docker) | The API and the web terminal at one address (`src/orbit/cloud.py`): pulls the data and results every 5 minutes, pushes your decisions within seconds, hands RUN ANALYSIS to GitHub | Always, but it sleeps after 48 hours without a visit (about a minute to wake) |

**Deployments are automatic.** Every push to `main` runs CI (Python tests on Windows, macOS and Linux; web typecheck, lint, tests and build; a build of the Space's image). When CI passes, the `deploy space` workflow puts that commit on the Space, and Hugging Face rebuilds it. Pull requests get the same CI but don't deploy.

**Why a separate private repo for the data:** this code repo is public, which keeps GitHub Actions free with no minute limit. Your journal (decisions and notes) must not be public, so the data lives in a private repo, reached with a token.

### One-time setup

The repo owner (`withaphelion-afk`) does this, because tokens can only reach repos their owner controls. Never paste a token into a chat or a file. Put it only in the secret fields below.

1. **Create the data repo.** On GitHub: New repository → `orbit-data` → **Private**, no README. Then, from a machine with this repo cloned, move the existing data there:
   ```bash
   git fetch origin data
   git push https://github.com/withaphelion-afk/orbit-data.git origin/data:refs/heads/data
   ```
2. **Data token.** GitHub → Settings → Developer settings → Fine-grained tokens → Generate. Repository access: **only `orbit-data`**. Permissions: **Contents: Read and write**. Copy it.
3. **Configure the code repo's Actions.** In `orbit`: Settings → Secrets and variables → Actions:
   - Secrets: `ORBIT_DATA_TOKEN` = the data token. `HF_TOKEN` = a Hugging Face token with **write** access (huggingface.co → Settings → Access Tokens).
   - Variables: `ORBIT_DATA_REPO` = `withaphelion-afk/orbit-data`. `HF_SPACE` = `your-hf-username/orbit`.
4. **Create the Space.** huggingface.co → New Space → name `orbit`, SDK **Docker** (blank template), visibility **Private**. Only you can open it, which is the terminal's login. In the Space's Settings → Variables and secrets:
   - Secret `ORBIT_DATA_TOKEN`: the same data token.
   - Secret `ORBIT_DISPATCH_TOKEN`: a second fine-grained token with repository access **only `orbit`** and permission **Actions: Read and write**. It lets RUN ANALYSIS start the workflow.
   - Variable `ORBIT_DATA_REPO` = `withaphelion-afk/orbit-data`.
5. **First run.** In `orbit` → Actions, run **runner**, then **analysis**, then **deploy space** (each has a "Run workflow" button). After that everything runs by itself.
6. **PCs that still run Orbit locally** should use the private repo too, or they'll keep syncing to the old public branch. On each one, run `git remote add data https://github.com/withaphelion-afk/orbit-data.git` and put `ORBIT_DATA_SYNC_REMOTE=data` and `ORBIT_DATA_SYNC_JOURNAL=1` in `.env`. Don't keep a PC runner going as well, or two hosts will do the same work.
7. Once the jobs run, the public `data` branch on `orbit` can be deleted.

### Things to know

- **GitHub turns off scheduled workflows after 60 days with no activity in the repo.** The jobs write to `orbit-data`, not here, so after two quiet months re-enable `runner` and `analysis` from the Actions tab (GitHub emails a warning first).
- **This repo's Actions logs are public.** They show prices, regime and counts, never your journal.
- **Scheduled jobs can start a few minutes late** when GitHub is busy. The SYS screen shows the last cycle and the next analysis.
- **Binance through `data-api.binance.vision`.** `api.binance.com` refuses US addresses, which is where GitHub's and Hugging Face's servers are. The mirror serves the same market data. `scripts/probe_sources.py` (or the `probe sources` workflow) checks every price source from a given host.

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

- `core/types.py` — shared data model (`Candle`, `Signal`, `TradeSuggestion`, `JournalEntry`, `Regime`, `FeatureRecord`) — done.
- `data/history.py` — full daily history per asset, stitched across venues and then updated incrementally — done.
  - BTC: Bitstamp from 2013, then Binance from Aug 2017.
  - ETH: Coinbase from May 2016, then Binance from Aug 2017.
  - SOL: Binance from Aug 2020.
  - Silver: Dukascopy spot XAG/USD from May 2003 (Yahoo only serves 2 years of hourly silver, and futures jump at every contract roll). `scripts/backfill_silver.py` downloaded it once (the feed throttles hard, so it's paced, cached and resumable); the runner tops it up each cycle, and the cache is shared on the `data` branch so no other machine has to download it again. Complete since Sept 2026: 6,063 daily and 140,899 hourly bars, all spot.
  - Hourly bars too, from the same venues: BTC 2013+ (~120k bars), ETH 2016+, SOL 2020+, silver 2003+.
  - Before joining two venues it checks that their closes agree over the overlap (currently a median gap of about 0.45%) and refuses if they don't. Every bar records its source, and each build writes `data/history_report.json`.
  - Fetchers live in `data/binance.py`, `bitstamp.py`, `coinbase.py` and `silver.py`, sharing a retrying HTTP helper. Run with `uv run python scripts/fetch_data.py`.
- `vedic/` — the Vedic (Jyotish) layer, the only astrology Orbit uses — done:
  - `sky.py`: sidereal longitudes and speeds of the 9 grahas (Surya, Chandra, Mangal, Budh, Guru, Shukra, Shani, Rahu, Ketu) from NASA JPL's DE421 via Skyfield, in the Lahiri / true-Chitrapaksha ayanamsa (Spica fixed at 0° Libra: 23.84° at J2000). Rahu is the mean node with precession removed; Ketu is opposite. Sampled every 6 hours from 2000 to 2028 and cached (`data/vedic/sky.npz`).
  - `zodiac.py`: the rules: 12 rashis, 27 nakshatras (4 padas each), uchcha/neecha, graha drishti (every graha the 7th; Mangal 4th and 8th, Guru 5th and 9th, Shani 3rd and 10th, Rahu/Ketu 5th and 9th), asta orbs (with the vakri orbs for Budh and Shukra), graha yuddha, malefics and benefics.
  - `events.py`: ~33,000 events, each refined to the second by bisection: rashi and nakshatra ingresses, vakri/margi stations, yuti, drishti, asta, graha yuddha, amavasya, purnima, surya and chandra grahan, named yogas (Kaal Sarp / Kaal Amrit, Gajakesari, Shani-Mangal), and malefic/benefic clusters. Checked against known dates (Shani into Meena 29 Mar 2025, Rahu into Kumbha 18 May 2025, the 2024-26 eclipses, Makar Sankranti).
  - `states.py`: the daily Vedic state of the sky (285 states: vakri, asta, rashi placements, dignity, yuti, drishti, yogas, paksha, eclipse windows) for the chop track and the model.
  - `scripts/fetch_ephemeris.py` builds the sky and events.
- `data/storage.py` — save/load candles and ephemeris snapshots as CSV under `data/` — done.
- `features/store.py` — the feature store: append-only CSV per asset, long format (date, name, value) — done.
- `features/technical.py` — daily return, close vs. 50/200-day SMA, 20-day volatility, computed as numpy rolling windows so full histories stay fast — done.
- `features/regime.py` — the regime gate (BTC+ETH 50/200-day SMA trend, both must agree for BULL/BEAR or it's CHOPPY) plus `compute_regime_series` to log its full history, not just a live reading — done.
- `features/astro.py` — each graha's sidereal rashi, vakri and asta, plus the Moon's nakshatra, as daily features per asset — done.
- `scripts/compute_features.py` — runs the full pipeline (technical + regime + Vedic) into the feature store — done.
- `data/pipeline.py` + `features/pipeline.py` — the fetch and feature-computation steps, refactored into reusable functions so scripts and the runner share the same logic.
- `runner/loop.py` — the 24/7 loop: on an interval, fetches fresh data, recomputes features, checks the strategy for a new suggestion and resolves outcomes, and logs the current regime. Wrapped so a single failed cycle (network blip, rate limit) is logged and retried, never crashes the process. It writes a heartbeat (`data/runner_status.json`) that the API reports — done, verified against real data end to end.
- `analysis/` — the Vedic playbook: every event type and combination above, outcomes over several forward horizons, significance tests, confidence labels, exception context and a chop track — done. Each event has its exact moment to the second and an hourly drill-down from it. `analysis/model.py` also asks the combined question: does knowing the whole Vedic sky improve a forecast? See "Astro research track" below for method and findings.
  - Run it from the web terminal (**RUN ANALYSIS** on ASTRO → PLAYBOOK, or on SYS), from the runner's daily schedule, or with `uv run python scripts/build_playbook.py`.
  - Runs from the button and the schedule are background jobs (`analysis/jobs.py`): one at a time, with live progress, a log, and a record of which labels changed.
- `strategy/rsi_divergence.py` — the one active strategy, RSI(14) divergence on daily bars — done. See "Strategy, backtest, journal and feedback loop" below.
- `backtest/engine.py` — replays the strategy over every asset's full history with costs; re-run on every analysis run — done.
- `journal/store.py` + `strategy/live.py` — suggestions from the latest completed bar, your decisions, and every suggestion followed to its outcome automatically (taken or not) — done.
- `strategy/calibrate.py` — the feedback loop: learns which divergences worked, retrained on every analysis run with backtest and live outcomes — done.
- `backtest/drift.py` — live results vs. the backtest's expectation, as a z-score — done.
- `api/` — FastAPI server the web terminal reads: stored data, the playbook, suggestions and decisions, the journal, backtest, feedback loop, drift, the Vedic model, runner status, and live prices over `/ws` — done. Run with `uv run python -m orbit.api` (or `scripts/start_orbit.py`).
- `web/` — the React trading terminal, on real data only — done. It has a command line with a Ctrl+K palette and F-key screens:
  - MON: chart and watchlist
  - GP: live TradingView chart, or Orbit's full-history chart with divergence, regime and Vedic markers
  - SUGG: suggestions to take, skip or modify
  - JRNL: every decision and outcome, including what skipped suggestions would have returned
  - DRIFT: live vs. backtest, the full backtest, and the feedback loop
  - ASTRO: the Vedic sky, event calendar, playbook, chop track and model
  - SYS: runner, layers, feeds, log and config
- `launcher.py` — `scripts/start_orbit.py`, `stop_orbit.py` and `autostart.py`: the same commands on Windows, macOS and Linux — done.
- CI/CD (`.github/workflows/`) — `ci.yml`: Python tests on Windows, macOS and Linux, the web typecheck, lint, tests and build, and a build of the Space image, on every push to `main` and every pull request. `deploy-space.yml`: deploys `main` to the Hugging Face Space once CI passes. `runner.yml` (hourly) and `analysis.yml` (daily) are the cloud host — done.
- `cloud.py` + `outputs.py` + `deploy/hf-space/` — free cloud hosting with no PC on (see [Free cloud hosting](#free-cloud-hosting-no-pc-needed)) — done.
- Alerts (Telegram) and position sizing — not started yet.

### Running the 24/7 runner

```bash
uv run python -m orbit.runner.loop
```

`scripts/start_orbit.py` starts this for you. Runs forever, re-checking every hour by default (`RUNNER_INTERVAL_SECONDS` in `config/settings.py` — daily candles don't produce new data more often than that anyway). Each cycle also creates a suggestion if an RSI divergence confirmed on the latest completed bar, expires undecided ones, and resolves outcomes. Logs go to console and `data/logs/runner.log`.

It also starts the analysis every day at **00:30 UTC** (`ANALYSIS_DAILY_AT_UTC`), after refreshing data so the new daily bar is included. Sunday's run also runs the placebo check (`PLACEBO_WEEKDAY`). If the machine was off at 00:30, it catches up as soon as the runner is up that day. It skips the run when one already succeeded after that day's slot, and retries a failed run at most 3 times, an hour apart. The schedule lives in the runner rather than the OS, so it works the same everywhere. Each run rebuilds the playbook, backtests the strategy, retrains the feedback loop and re-checks the Vedic model.

### Running the web API (backend for the React frontend)

```bash
uv run python -m orbit.api        # or, while developing: uv run uvicorn orbit.api.app:app --reload
```

Serves on `http://127.0.0.1:8000` by default, and also serves the built web terminal (`web/dist`) there. `web/vite.config.ts` proxies `/api` and `/ws` to it during UI development. Run the Getting started scripts first so there's real data for it to serve. The web terminal always reads this API; there is no mock mode.

It only reads what the scripts and runner have stored; it never fetches history or runs research itself. The exceptions: live prices (a background task polls Binance and Yahoo for silver, and pushes each tick over `/ws`), starting an analysis run, and logging your decision on a suggestion, which writes the journal and never places an order.

Reports that don't exist yet (no backtest before the first analysis run, say) answer `404` with an explanation, and `/api/system` lists which layers exist. The full endpoint list is in [`web/README.md`](web/README.md).

## Strategy, backtest, journal and feedback loop

**The strategy** (`strategy/rsi_divergence.py`) is basic RSI(14) divergence on daily bars, with textbook parameters fixed before looking at any results:

- **Bullish:** price makes a lower swing low while RSI makes a higher low, and the first low had RSI under 40. **Bearish** is the mirror: a higher swing high with a lower RSI high, the first above 60.
- A swing is the lowest (highest) bar of the 5 before it and 3 after, so it is only known 3 bars later. The signal fires on that confirmation bar and uses nothing that wasn't known then (tested).
- The two swings are 5 to 60 bars apart. Stop: beyond the second swing by 0.5 ATR(14). Target: 2R. Out after 30 bars if neither is hit.

**The backtest** (`backtest/engine.py`) replays it over every asset's full stored history: entry at the next bar's open, stop assumed hit first when a bar touches both levels, gaps through a level exit at the open, one trade at a time per asset, and costs of 0.1% a side (0.05% for silver) plus 0.05% slippage. Results as of Sept 2026:

| | Trades | Win rate | Avg R | Profit factor | Max drawdown |
| --- | --- | --- | --- | --- | --- |
| All assets | 204 | 38.7% | −0.020R | 0.97 | −18.8R |
| BTC | 67 | 36% | −0.067R | 0.88 | −8.2R |
| ETH | 39 | 44% | −0.008R | 0.99 | −9.3R |
| SOL | 23 | 30% | −0.057R | 0.90 | −3.8R |
| Silver (spot, 2003 on) | 75 | 41% | +0.028R | 1.05 | −8.8R |
| Longs (all) | 71 | 39% | +0.080R | | |
| Shorts (all) | 133 | 38% | −0.073R | | |

In plain words: as a whole, basic RSI divergence is roughly break-even after costs. The bullish side has been positive (+0.08R a trade), the bearish side negative, and silver slightly positive. That is the honest starting point the feedback loop and your journal build on.

**Suggestions and the journal** (`strategy/live.py`, `journal/store.py`): after every data refresh, a divergence that confirmed on the latest completed bar becomes a suggestion in SUGG (entry at that bar's close, the stop and 2R target, the signals behind it). You take, skip or modify it; undecided suggestions expire after 3 bars. Every suggestion is then followed to its outcome automatically with the strategy's own levels, whether you took it or not, so the journal shows what skipped ones would have returned. Taken or modified ones are also followed with the levels you used. The journal is `data/journal/suggestions.json` on each machine, written atomically with a dated daily backup.

**The feedback loop** (`strategy/calibrate.py`): a small logistic model learns which divergences actually won, from what was known at the signal: divergence size, RSI level, the price move between the swings, their distance apart, ATR, volatility percentile, trend agreement, and long vs. short. It trains on every backtest trade plus every finished live suggestion (each counted 3×, as the most recent evidence), and is retrained on every analysis run. It is checked walk-forward (trained on earlier years, tested on the next), and it only sets a suggestion's confidence once it beats the plain win rate there. So far it doesn't (Brier 0.264 vs 0.252, AUC 0.53), so every suggestion's confidence is the plain win rate, about 39%. DRIFT → FEEDBACK shows this check after every run.

**Drift** (`backtest/drift.py`): live win rate vs. the backtest's, as a z-score, once there are 10 finished live suggestions. At 1σ it's WATCH; at 2σ it's DRIFT, the point to scale down.

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

### Astro research track (Vedic rules only)

Treated as one testable input among others — back-tested with the same rigor as technical signals, not taken on faith. All astrology in Orbit follows Vedic (Jyotish) rules: the sidereal zodiac with the Lahiri / Chitrapaksha ayanamsa, the 9 grahas, rashi-based graha drishti, and the classical yogas (see `vedic/` under Status).

- **Ephemeris source**: Skyfield with NASA JPL's DE421 (pure Python, no compiler needed), converted to sidereal longitudes. (Originally planned as Swiss Ephemeris via `pyswisseph`, but that needs a C++ compiler not available on this machine.)
- **Events tested**: each graha's rashi ingress (overall and into each rashi); the Moon's and Sun's nakshatra changes; vakri and margi stations; yuti (two grahas in one rashi); drishti (mutual 7th, and each special aspect by house); asta; graha yuddha; amavasya and purnima; surya and chandra grahan; the named yogas; and malefic or benefic clusters (several relations starting within a week).
- **Combinations**: yuti and drishti are tested per pair of grahas, and again with a `|VAKRI` variant when one of them was retrograde. Named yogas and clusters are combinations by definition. In total 419 patterns per asset.
- **Exact moments**: every event since 2000 is refined to the second by bisection, and dated on the UTC day it really happened.
- **Hourly drill-down**: from each exact moment, the same big-up / big-down / sideways test over 6, 24 and 72 hourly bars, with its own FDR family per asset. Each occurrence also records:
  - what price did in the 72 hours before
  - how many hours until price had moved one normal day's range (daily ATR) in the move's direction
  - when the largest move in that direction came, and its size

  The terminal shows each occurrence's hourly chart, with those points marked.
- **Outcomes**: forward returns over horizons that depend on how fast the grahas involved move:
  - Moon-driven events: 1, 3 and 5 bars
  - fast grahas and lunations: 1, 5, 10 and 20 bars
  - slow grahas only (Guru, Shani, Rahu, Ketu): 20, 40 and 60 bars

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
  - other events in the same window, and any that lean the opposite way
- **Chop track**: separately, which Vedic *states* (e.g. "Budh vakri", "Shani in Meena", "Kaal Sarp yoga") coincide with sideways markets. The sample size counted is distinct episodes, not days.
- **The Vedic model** (`analysis/model.py`): the combined question the playbook can't ask one pattern at a time. Does knowing the whole Vedic sky (all 285 daily states at once) make a forecast of big up, big down or sideways moves, 5 and 20 days ahead, better than price alone?
  - It is a ridge logistic regression, trained walk-forward: retrained every 2 years, always tested on the years after, with the ridge strength picked on the last 20% of each training window.
  - The price-only model uses 9 features: returns, volatility, trend and RSI.
  - The sky gets credit only if adding it beats price alone out-of-sample, **and** beats the same Vedic data shifted by about 2 and 4 years, **and** beats simply guessing the base rate, in most of the test years. The shifted controls have the same structure but can't know anything.
- **Validation**: `scripts/placebo_check.py` moves every event date (and exact moment) by arbitrary offsets and re-runs everything, daily and hourly; any moderate or strong result on those fake calendars is a false discovery. With the Vedic events it produces 0 of 32 (daily) and 0 of 32 (hourly timing), as it did before the switch (after fixing an earlier 6 of 32). A planted-effect unit test confirms the method still catches a real effect.
- **Findings so far (Sept 2026)**: 15,261 tests across four assets and 12 families, daily and hourly (silver's hourly timing included since its spot history arrived).
  - **No Vedic pattern survives multiple-testing correction for any asset, at daily or hourly resolution.** That is 0 strong and 0 moderate.
  - Some patterns are "weak" (nominally significant): BTC 60, ETH 41, SOL 23, silver 83 (daily); 57, 41, 36 and 73 (hourly timing). That is about the rate chance alone produces among that many tests.
  - The model: 24 targets checked (4 assets × big up / big down / sideways × 5 and 20 days ahead). 22 show no added skill.
    - SOL's big up moves 20 days ahead passed: +3.6% skill with the sky vs. −0.4% on price alone, better in all 3 test years, and beating the one control SOL's short history allows.
    - BTC's sideways 5 days ahead and silver's big down moves 20 days ahead are "unclear": a gain too small to beat simply guessing the base rate.
    - One or two passes out of 24 is what chance alone produces, so SOL's result is on watch, not trusted, until it holds on later runs.
  - Price alone has a small real edge on big up moves 5 days ahead (BTC: about 4% better than guessing the base rate, AUC ~0.61).
  - The playbook and model re-run every day. A pattern only counts once it clears the correction; the sky only counts once it beats the controls.

### Signal research reference

Notes from researching how professional quant systems structure this, so we build on established practice instead of guesswork:

- **Signal categories worth having**: price-action/technical (momentum, mean reversion, volatility), volume/liquidity, on-chain (crypto: exchange flows, MVRV, SOPR), derivatives positioning (crypto: funding rate, open interest), macro (silver: real yields, DXY, gold/silver ratio), positioning (silver: CFTC COT report — released with a lag, watch for look-ahead bias), cross-asset correlation.
- **Telling a real signal from noise**: keep out-of-sample data untouched until final testing; use walk-forward validation (fit on a rolling past window, test on the next period, roll forward); watch for look-ahead bias (only use data available at decision time); correct for multiple testing — the more variants tried, the more likely the best result is luck (a new factor should arguably clear a t-stat of 3.0, not 2.0). For small-sample effects like astro transits specifically: write the hypothesis down *before* looking at the data, log every transit tested as a trial count, use permutation tests (shuffle event dates thousands of times, see how often random dates beat the real result), and treat ~10-30 historical events as "worth monitoring," never "proven."
- **Combining signals**: convert each to a z-score (standard deviations from its own average) and combine with weights close to equal — optimized weights tend to overfit. Uncorrelated signals add real value; five signals all measuring momentum are worth about one. Regime-conditional models (classify the market state first, then decide which signals/exposures apply) are the standard structure — confirms our regime-gate + per-asset-entry design matches how real quant shops work. One caveat: regime classifiers are slow to recognize a *new* regime, so the gate itself needs testing too, not just what sits on top of it.
- **Feature store concept**: a central, timestamped table of computed signals sitting between raw data and strategy logic — ingestion writes raw data, features are computed once and "point-in-time correct" (timestamped with when they'd actually have been knowable), and strategies only ever read features, never raw data directly. Stops indicators being recomputed slightly differently in different places and prevents look-ahead leakage. This is the model for our own `features/` layer.

### Build plan

| Phase | Description | Status |
| --- | --- | --- |
| 1. Define the strategy | Assets, timeframe, entry/exit rules, risk rules on paper | Done: RSI(14) divergence, daily, all four assets; position sizing not yet |
| 2. Data pipeline | Price data + ephemeris data, stored locally | Done: full stitched histories, incremental updates, ephemeris 2 years ahead |
| 3. Backtest engine | Walk-forward validation; test astro factors for significance | Done: full-history strategy backtest with costs; Vedic playbook and model (placebo-checked, walk-forward) |
| 4. Trade journal + scorecard | Logging schema for every signal and decision | Done: every suggestion, decision and outcome, including skipped ones |
| 5. 24/7 runner | Always-on service, evaluates on schedule, logs/alerts, no execution | Done: hourly on GitHub Actions (or on a PC via `scripts/start_orbit.py`); alerting not started |
| 6. Feedback loop | Review cadence to correct/reweight the scorecard | Done: retrained on every analysis run; sets confidence only once it beats the plain win rate out-of-sample |
| 7. Auto-execution | Enabled later, once confidence is earned | Not started |
| Web terminal | Dashboard for suggestions, decisions, journal, drift and runner status | Done, on real data via `api/` |
| CI | Tests on every push and pull request | Done: Python on Windows, macOS, Linux; web typecheck, lint, tests, build |

### Open decisions

- **Project name**: working title **Orbit** (used for the astro-transit + always-on-monitoring theme).
- **Strategy definition**: settled for now: basic RSI(14) divergence (above). Refinements should come from the journal and the feedback loop, one change at a time, each re-backtested.
- **Hosting**: settled: free cloud, no PC. GitHub Actions runs the runner (hourly) and analysis (daily), a private `orbit-data` repo holds the data and results, and a private Hugging Face Space serves the terminal. PCs can still run Orbit locally with `scripts/start_orbit.py`.
- **Sharing the journal**: settled: through the private `orbit-data` repo (see Free cloud hosting).
- **Journal fields**: settled: `JournalEntry.outcome_pnl` is the percent return net of costs on the levels you acted on; journal rows add `counterfactual_pnl` (what a skipped or expired suggestion would have returned), `expired`, and `exit_reason`.
- **Position sizing and alerts**: next to decide.
