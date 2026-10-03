# Orbit — Systematic Trading Strategy

A 24/7 systematic trading assistant for **BTC, ETH, SOL and silver**. It watches the markets, suggests trades with a stated confidence, and logs what you decide. It never places an order: auto-execution stays off until the system has earned trust.

It also runs a research track that tests, with strict statistics, whether Vedic astrology predicts price moves. So far it doesn't (see [Research findings](#research-findings)).

This is a learning project too: modules are written to be read, and comments explain *why*.

**Two ways to run it:**
- **In the cloud, free, with no PC on.** GitHub Actions does the work, and the web terminal is an installable app at **https://orbit-inky-psi.vercel.app**. See [Cloud](#cloud-free-no-pc-needed).
- **On your own machine** (Windows, macOS, Linux), with a live local server. See [Run it on your machine](#run-it-on-your-machine).

## Core ideas

- **One strategy at a time.** No competing strategies until one is proven.
- **Your experience becomes rules.** Intuition gets written down as explicit, testable logic.
- **Self-correcting.** Live results are checked against the backtest's expectation, and the system flags drift.
- **Suggestions, not autopilot.** Every trade idea comes with its reasoning, for you to take, skip or modify.

## What it does

| Part | What | Where |
| --- | --- | --- |
| Data | Full daily and hourly price history per asset, stitched across venues and updated incrementally | `data/` |
| Vedic sky | Sidereal positions of the 9 grahas and ~33,000 events (ingresses, stations, yuti, drishti, eclipses, yogas), each timed to the second | `vedic/` |
| Features | Returns, trend vs. 50/200-day averages, volatility, the BTC/ETH regime gate, Vedic states | `features/` |
| Research | The Vedic playbook (every event type and combination, with significance tests) and the Vedic model | `analysis/` |
| Strategy | RSI divergence on 1H/4H/1D/1W, scored by a self-learning model; alerts on all four, suggestions on 4H and 1D | `strategy/` |
| Backtest | The strategy over full history with costs, and live-vs-backtest drift | `backtest/` |
| Journal | Every suggestion, your decision, and its outcome, including what skipped ones would have returned | `journal/` |
| Feedback loop | The model retrains hourly on every divergence the market graded plus your ✓/✗; trusted only once it beats the plain rate out of sample | `strategy/divergence_model.py` |
| Runner | Data → features → suggestions every hour; the analysis daily at 00:30 UTC | `runner/` |
| Web terminal | Keyboard-first terminal: chart, watchlist, suggestions, journal, drift, astro research, system | `web/` |

Not built yet: alerts (Telegram), position sizing, auto-execution.

## Cloud (free, no PC needed)

There is no server. GitHub Actions jobs do all the work and publish their results. The web terminal is a static app that reads them.

| Where | What | When |
| --- | --- | --- |
| GitHub Actions `runner` | One runner cycle: new bars, features, the divergence model retrained and scored, alerts, suggestions created/expired/resolved; then publishes | Hourly, started by **cron-job.org** (see setup step 4); GitHub's own schedule skipped most runs, so it's off |
| GitHub Actions `analysis` | Playbook, backtest, feedback loop and Vedic model (placebo check on Sundays); then publishes | Daily 00:30 UTC, and from RUN ANALYSIS |
| GitHub Actions `decide` | Logs your Take / Skip / Modify in the journal; then publishes | When you click it |
| GitHub Actions `label` | Saves your ✓ real / ✗ not real on a divergence, for the next retrain | When you click it |
| Private repo `orbit-data` | `data`: prices, silver cache, kernel, journal. `outputs`: computed results. `site`: every API answer as a JSON file, for the web terminal | Written by every job |
| Vercel | The web terminal (installable), plus its small login service (`web/vercel/api`) | Deployed after every green CI run on `main` |

**Your data stays private behind one login.** The app on Vercel holds no data. After you log in, its login service reads the `site` branch of the private `orbit-data` repo, and starts the `decide`, `label` and `analysis` jobs, with a GitHub token that stays on Vercel's side and never reaches a browser.

### Using the web terminal

1. Open **https://orbit-inky-psi.vercel.app** (the Vercel project `orbit`; each **deploy web** run also prints it).
2. **Install it:** in Chrome, click the install icon at the right of the address bar (or ⋮ → Cast, save and share → Install page as app). It then opens in its own window like a desktop app, with its own icon. On Android: ⋮ → Add to Home screen.
3. **Log in** with the shared username and password (default **`saksham` / `00000000`**). The same login works on every device, and each device stays logged in for 30 days. To change it, set the variable `ORBIT_LOGIN_USER` and the secret `ORBIT_LOGIN_PASSWORD` in `orbit` → Settings → Secrets and variables → Actions; it applies from the next deploy. The defaults are visible in this public repo, so a stronger password is safer.

What updates when:
- **Live prices** for BTC, ETH and SOL come straight from Binance in your browser. Silver shows its last stored close.
- **Everything else** is as fresh as the last runner job, hourly.
- **Take / Skip / Modify** reaches the journal in about 1–5 minutes, and an analysis run in about 20 (60 with the placebo check).

### One-time setup

Done by the repo owner (`withaphelion-afk`), because tokens can only reach repos their owner controls. Never paste a token into a chat or a file, only into the secret fields below. The GitHub web form is the reliable way: a hidden terminal prompt on Windows has saved empty values before.

1. **Data repo** (done 3 Oct 2026; kept here to rebuild it):
   ```bash
   gh repo create withaphelion-afk/orbit-data --private
   ```
   Seed it from a machine that has the data: `python scripts/sync_data.py --recreate` with `ORBIT_DATA_SYNC_REMOTE=data`.
2. **Secrets and variable** in `orbit` → Settings → Secrets and variables → Actions:
   - Secret `ORBIT_DATA_TOKEN`: fine-grained token, repository access **`orbit-data` and `orbit`**: **Contents: Read and write** (the jobs write the data) and **Actions: Read and write** (the site's login service starts `decide`, `label` and `analysis` with it). Without the Actions permission the site still shows everything, but Take/Skip, ✓/✗ and RUN ANALYSIS fail.
   - Secret `VERCEL_TOKEN`: a Vercel token (vercel.com → Account Settings → Tokens).
   - Variable `ORBIT_DATA_REPO` = `withaphelion-afk/orbit-data`.
3. **Start it:** in Actions, run **runner** (it publishes the data), then **deploy web** (it creates the Vercel project `orbit`). Deploying also hands the login service its settings: the token from `ORBIT_DATA_TOKEN` and the login.
4. **Hourly runner trigger** (cron-job.org, free). GitHub's own schedule skipped most runs, so an outside timer starts the runner:
   - Make a fine-grained token with repository access **only `orbit`** and **Actions: Read and write**, with an expiry date (renew it before then).
   - In cron-job.org, create a job by **importing this curl**, with your token pasted in:
     ```bash
     curl -X POST "https://api.github.com/repos/withaphelion-afk/orbit/actions/workflows/runner.yml/dispatches" -H "Accept: application/vnd.github+json" -H "Authorization: Bearer YOUR_GITHUB_TOKEN" -H "X-GitHub-Api-Version: 2022-11-28" -H "Content-Type: application/json" -d "{\"ref\":\"main\"}"
     ```
   - Schedule: **every hour at minute 17**. Success is **204** (empty answer); turn on failure emails. Two runs never overlap, so an extra trigger is harmless.

### Things to know

- **Scheduled jobs:** only `analysis` (daily 00:30 UTC) still uses GitHub's schedule. GitHub turns schedules off after 60 days with no activity in the repo; the analysis job re-enables itself, which resets the clock. If it ever stops for 60 days, re-enable it in the Actions tab.
- **Until the setup is done**, `runner`, `analysis` and `decide` are skipped (not failed): they wait for the `ORBIT_DATA_REPO` variable. `deploy web` does nothing until `VERCEL_TOKEN` is set.
- **This repo's Actions logs are public.** They show prices, the regime and counts, never your journal.
- **If RUNNER shows STALE on the site**, the hourly trigger stopped: check the cron-job.org job's history (an expired token gives 401). You can always run **runner** by hand from the Actions tab.
- **Binance through `data-api.binance.vision`:** `api.binance.com` refuses US addresses, which is where GitHub's servers are. The mirror serves the same market data. `scripts/probe_sources.py` (or the `probe sources` workflow) checks every price source from a given host.

## Run it on your machine

**1. Install three tools (once):** [git](https://git-scm.com/downloads) (log in to GitHub once, e.g. `gh auth login`), [uv](https://docs.astral.sh/uv/getting-started/installation/) (installs Python and every package), and [Node.js 20.19+](https://nodejs.org) (builds the web terminal).

**2. Start it:**
```bash
git clone https://github.com/withaphelion-afk/orbit.git
cd orbit
uv run python scripts/start_orbit.py
```
Or double-click `start_orbit.cmd` (Windows) or run `./start_orbit.sh` (macOS/Linux). The first start:
1. creates `.venv` and builds the web terminal;
2. takes the shared data from GitHub;
3. starts the API and the runner in the background;
4. opens http://127.0.0.1:8000.

The first analysis run takes 15–20 minutes. Until then, its screens say they haven't been generated yet.

**3. Every day:**

| To | Run |
| --- | --- |
| Start (safe when already running) | `uv run python scripts/start_orbit.py` |
| Check | `uv run python scripts/start_orbit.py --status` |
| Stop | `uv run python scripts/stop_orbit.py` |
| Start at login (`--remove` to undo) | `uv run python scripts/autostart.py` |
| Sync the shared data now | `uv run python scripts/sync_data.py` (`--pull`, `--status`) |
| Update | `git pull`, then stop and start |

The cloud is the host now, so a PC running the runner too would duplicate its work. To use the private data repo, run `git remote add data https://github.com/withaphelion-afk/orbit-data.git` and put `ORBIT_DATA_SYNC_REMOTE=data` and `ORBIT_DATA_SYNC_JOURNAL=1` in `.env`.

**If something doesn't work:**

| What you see | What to do |
| --- | --- |
| `No .venv yet. Install uv` | Install uv and start again. |
| `Node.js/npm not found` | Install Node.js 20.19+. Everything else runs meanwhile, without the web terminal. |
| `--status` says running, but SYS shows NEVER_RUN or STALE | Stop Orbit, delete `data/runner_status.json` and `data/run/`, start again. |
| Price errors from a venue (HTTP 451/403) | Run `uv run python scripts/probe_sources.py`. This machine still gets every price through the sync. |
| `Couldn't send this machine's data` | This machine can read GitHub but not write. It still receives everything. |
| Port 8000 in use | Put `ORBIT_API_PORT=8001` in `.env`. |

Logs are in `data/logs/`: `api.out`, `runner.out`, `silver.out` and `runner.log`.

**Windows with Smart App Control:** it blocks pandas' compiled files, so nothing in Orbit uses pandas; the maths is numpy, and the launcher uses only the standard library.

## Shared data

What can't be rebuilt in seconds is shared through branches of the private data repo (`ORBIT_DATA_SYNC_REMOTE`; the default remote `origin` only suits a private code repo):

| Branch | Holds | Written by |
| --- | --- | --- |
| `data` | Price histories (`{ASSET}_{1d,1h}.csv`, `history_report.json`), the spot-silver cache, NASA's DE421 kernel, the placebo check, the journal | `datasync.py`: merged file by file |
| `outputs` | Computed results: playbook, backtest, calibration, Vedic model and sky, runner status | `outputs.py --publish`: replaced each time |
| `site` | Every API answer as JSON, for the web terminal | `snapshot.py` + `outputs.py --site`: replaced each time |

**How `data` merges** (`datasync.py`): it fetches the branch, merges it with `data/` by rules (never git merges, so no conflicts), writes each winner to both sides and pushes. If another machine pushed meanwhile, it merges again.
- **Prices:** the better file wins. For silver, spot beats futures; then the longer history; then the later last bar. To publish a deliberate rebuild, use `--prefer-local`.
- **Silver cache and kernel:** files are only ever added.
- **Placebo check:** the newer one wins.
- **Journal:** merged by suggestion, and a decision beats an undecided one. If both machines decided, the first decision stands and the other is kept in its notes. The local journal is backed up before a sync changes it.

The journal is shared only when `ORBIT_DATA_SYNC_JOURNAL=1`, and only ever with a private repo. `ORBIT_DATA_SYNC=0` turns syncing off. Tests never sync (`tests/conftest.py`).

`outputs` and `site` are single commits, force-pushed each time, so ~50 MB of daily results never builds up history. Each push sends only the files that changed.

## Project layout

```
orbit/
  src/orbit/
    data/         price fetchers (Binance, Bitstamp, Coinbase, Dukascopy, Yahoo quote), stitching, storage
    vedic/        Vedic rules: sidereal sky, grahas, events, drishti, yogas, daily states
    features/     returns, trend, volatility, regime gate, Vedic features
    analysis/     the playbook, significance, the Vedic model, analysis runs
    strategy/     RSI divergence, live suggestions, the feedback loop
    backtest/     full-history backtest, live-vs-backtest drift
    journal/      suggestions, decisions, outcomes (and a CLI for the cloud `decide` job)
    runner/       the 24/7 loop and its daily schedule
    api/          FastAPI server: the terminal's API and live prices over /ws
    snapshot.py   every API answer as static files (the cloud terminal's data)
    datasync.py   shares the data branch;  outputs.py: the outputs and site branches
    launcher.py   start/stop/status/autostart on any OS
    config/       settings (config/settings.py; secrets via .env)
    core/         shared types (Candle, Signal, TradeSuggestion, JournalEntry, ...)
    alerts/       not built yet
  web/            the React terminal (web/README.md); src/api/static.ts is the cloud data client
  scripts/        start/stop/autostart, data and research scripts
  tests/          Python tests
  .github/        CI, deploy, and the runner / analysis / decide jobs
```

## Development

```bash
uv sync --extra dev
uv run pytest -q                       # never touches GitHub
cd web && npm install && npm run dev   # http://localhost:5173, proxied to the local API
```

The data and research scripts can be run by hand (the runner does all of this):

```bash
uv run python scripts/fetch_data.py        # full daily + hourly history (incremental after the first run)
uv run python scripts/fetch_ephemeris.py   # the Vedic sky 2000-2028 and its events (~30 s)
uv run python scripts/compute_features.py  # technical, regime and Vedic features
uv run python scripts/build_playbook.py    # the Vedic playbook (~5 min), or RUN ANALYSIS
uv run python scripts/placebo_check.py     # sanity check of the playbook method (~40 min)
uv run python scripts/backfill_silver.py   # the spot-silver download (shared already; resumable, takes hours)
```

**CI/CD:** every push and pull request runs `ci.yml`, which covers Python tests on Windows, macOS and Linux, plus the web typecheck, lint, tests and build. When CI passes on `main`, `deploy-web.yml` builds the static terminal (`VITE_ORBIT_STATIC=1`) and deploys it to Vercel.

**Local task runner** (`scripts/dev.py`, standard library only, no tokens):

```bash
uv run python scripts/dev.py check          # all Python + web tests, typecheck, lint, build; PASS/FAIL summary
uv run python scripts/dev.py ship "msg"     # commit to a new branch, push, open a PR (CI checks it)
uv run python scripts/dev.py deploy [PR]    # runs check first; merges into main only if everything passes
uv run python scripts/dev.py install-hook   # run check automatically before any push to main
uv run python scripts/dev.py status | cleanup | start | stop
```

The full check runs only on the way to `main` (via `deploy` or the pre-push hook), since `main` is what Vercel deploys.

**Conventions:**
- One strategy at a time.
- Settings live in `config/settings.py`.
- Keep modules testable as pure functions where possible.
- `web/src/api/types.ts` mirrors `core/types.py` and `api/schemas.py`: change them together.
- No pandas in `src/`.

## Strategy, backtest, journal and feedback loop

**Finding divergences** (`strategy/divergence.py`, and the same algorithm in `web/src/lib/divergence.ts`):
- **Timeframes:** 1H, 4H (built from 1H), 1D and 1W (built from 1D), for every asset.
- **Broad on purpose:** swings are loose (2 bars each side, each with a strength), and every pair of swings 5–60 bars apart where price and RSI(14) disagree is a candidate. That covers regular divergences and hidden ones, with no RSI-zone rule and no ATR. The model decides which matter.
- **One algorithm, two languages:** the backend (training, backtest, suggestions) and the browser (live chart) must find exactly the same divergences. `tests/fixtures/divergence_cases.json` is checked by both test suites, so CI fails if they ever disagree.

**Learning which ones matter** (`strategy/divergence_model.py`):
- **The market grades every divergence:** it worked if price moved the asset's own top-25% move for that timeframe in its direction within the horizon (1H: 24 bars, 4H/1D: 30, 1W: 12), before moving the same distance against it.
- **You teach it:** ✓ real / ✗ not real on the ORBIT chart and in ALERTS, or mark one it missed by clicking its two swings. Your label overrides the market's grade and counts 5×. Labels are saved in the private data repo (`journal/divergence_labels.json`).
- **Training:** a numpy logistic model on what was known at confirmation (the two swings' RSI, the size of the disagreement, swing strength, bars between, kind, direction, volume trend, the trend before, the BTC/ETH regime, the volatility percentile, timeframe and asset). It retrains on every runner cycle.
- **Honesty:** a walk-forward check scores it on later divergences it never saw. It's marked trusted only once that beats always guessing the plain rate. Until then every score shows as "unproven". Today: 153,481 graded divergences, 24.5% worked, out-of-sample Brier 0.183 vs 0.181 for the plain rate (AUC 0.51). **Unproven.**
- **Alerts:** a confirmed divergence scoring in the top 20% of its timeframe (`DIVERGENCE_ALERT_QUANTILE`) raises an alert: a badge, a snackbar and a row in ALERTS (F9). The browser raises them the moment one confirms on the open chart, and the runner hourly for every asset. 1H and 1W are alerts only. 4H and 1D also become suggestions.

**The backtest** (`backtest/engine.py`), per timeframe, never mixed:
- **Which trades:** only divergences whose *out-of-sample* score reached the alert threshold. The model never saw what came next.
- **Execution:** entry at the next bar's open, stop at the second swing's extreme (no ATR), target 2R, out after the timeframe's horizon. When a bar touches both levels, the stop is assumed hit first; a gap through a level exits at the open. One trade at a time per asset.
- **Costs:** 0.1% a side (0.05% for silver), plus 0.05% slippage.

Results as of Oct 2026:

| | Trades | Win rate | Avg R | Profit factor | Max drawdown |
| --- | --- | --- | --- | --- | --- |
| **1D**, all assets | 411 | 38% | +0.012R | 1.02 | −28.2R |
| 1D BTC / ETH / SOL / silver | 92 / 68 / 109 / 142 | 40 / 34 / 45 / 34% | +0.03 / +0.02 / +0.20 / −0.15R | | |
| 1D longs / shorts | 302 / 109 | | +0.057 / −0.113R | | |
| **4H**, all assets | 2,485 | 38% | −0.118R | 0.83 | −301.6R |
| 4H longs / shorts | 1,794 / 691 | | −0.092 / −0.185R | | |

In plain words: on 1D the learned selection is about break-even after costs. Longs are positive and SOL is the best, but silver and shorts lose. On 4H it loses steadily. The model isn't better than chance yet, so these numbers are close to "take every divergence". Your ✓/✗ labels are what should move them.

**Suggestions and the journal:**
- **Where they come from:** a 4H or 1D alert that confirmed on the latest completed bar becomes a suggestion in SUGG. Entry is that bar's close, the stop is at the swing extreme, and the target is 2R.
- **Your decision:** take, skip or modify it. An undecided suggestion expires after 3 bars of its own timeframe: 12 hours on 4H, 3 days on 1D.
- **Outcomes:** every suggestion is followed to its outcome on the strategy's levels, taken or not, so the journal shows what skipped ones would have returned. Taken or modified ones are also followed on the levels you used. JRNL has a timeframe column and filter.

**Drift** (`backtest/drift.py`): live win rate vs. the backtest's, per timeframe (4H and 1D apart), as a z-score, from 10 finished live suggestions. At 1σ it's WATCH; at 2σ it's DRIFT, the point to scale down.

## Research findings

**Projections** (ASTRO → PROJECTIONS, the default tab; `analysis/projections.py`):
- **What it shows:** every upcoming Vedic event per asset, with what followed it in the past. That covers the projected outcome, the odds against normal with a 95% range, size, timing, N and the honesty label.
- **Trust:** only STRONG or MODERATE patterns are presented as trusted. Today none are, so every row says "unproven, not significant".
- **Grouping:** overlapping events are grouped, and opposite projections are flagged.
- **Track record:** each projection is logged when made and graded after its window. That is a live test history-fitting can't fake.


**Method** (Vedic rules only: sidereal zodiac, Lahiri ayanamsa, 9 grahas, rashi drishti, classical yogas):
- **Patterns tested:** 419 per asset. They cover rashi and nakshatra ingresses, vakri/margi stations, yuti and drishti per pair (with a `|VAKRI` variant), asta, graha yuddha, amavasya and purnima, eclipses, named yogas, and malefic/benefic clusters.
- **Outcomes:**
  - Horizons follow the speed of the grahas involved: Moon 1/3/5 bars, fast grahas 1/5/10/20, slow grahas 20/40/60.
  - There's also an hourly test from each exact moment: 6/24/72 bars.
  - BIG_UP and BIG_DOWN are the asset's own top and bottom 15% of moves. SIDEWAYS is a small net move against ATR while the market still moved normally.
- **Significance:**
  - Each hit rate is compared with the whole event calendar shifted circularly against prices (via FFT, with a fitted negative-binomial tail).
  - Benjamini-Hochberg FDR correction runs per asset.
  - Alongside it, every test gets a Romano-Wolf (family-wise) p-value as a comparison column, and a diagnostic `neighbour_support` (does the effect also show at the horizons next to it?). Neither changes a label yet; the run's meta counts how many tests each would change.
  - Before an analysis run, stored prices are checked for holes (`data/gaps.py`): crypto has none to spare, silver's weekends and holidays are expected. A hole beyond the tolerance stops the run instead of shifting every window.
  - Patterns with fewer than 12 occurrences are never tested.
  - The hypotheses are written down before any test runs.
- **Labels:** strong (q ≤ 0.05, 25+ occurrences, 1.5× the base rate), moderate (q ≤ 0.10), weak (nominal p < 0.05 only).
- **Validation:** `scripts/placebo_check.py` re-runs everything on fake, shifted calendars: 0 of 32 false discoveries, daily and hourly. A planted-effect test confirms the method still finds a real effect.
- **The Vedic model** (`analysis/model.py`): does the whole sky (285 daily states) improve a 5- and 20-day forecast over price alone? It's a walk-forward ridge logistic regression, and the sky gets credit only if it beats price alone, sky data shifted by about 2 and 4 years, and the base rate, in most test years.

**Findings (Sept 2026), from 15,261 tests across four assets:**
- **No Vedic pattern survives multiple-testing correction for any asset, daily or hourly: 0 strong, 0 moderate.** The "weak" ones occur at about the rate chance alone produces, and they reshuffled when event timing was corrected.
- **The Vedic model:** 22 of 24 targets show no added skill. SOL's big up moves 20 days ahead passed once, but one or two passes in 24 is what chance produces, so it's on watch, not trusted.
- **Price alone** has a small real edge on big up moves 5 days ahead (BTC: about 4% better than the base rate, AUC ~0.61).

Both re-run daily; a pattern only counts once it clears the correction.

## Status and next steps

| Phase | Status |
| --- | --- |
| Strategy definition | Done: RSI divergence on 1H/4H/1D/1W with a self-learning model; suggestions on 4H and 1D |
| Data pipeline | Done: stitched full histories, incremental, ephemeris to 2028 |
| Backtest and research | Done: strategy backtest with costs; Vedic playbook and model, placebo-checked |
| Journal and feedback loop | Done: every suggestion and outcome; confidence only once proven out of sample |
| 24/7 runner and hosting | Done: free cloud (GitHub Actions + Vercel), or a PC |
| Web terminal | Done: live or static, installable |
| CI/CD | Done |
| Position sizing, alerts | Next to decide |
| Auto-execution | Later, once confidence is earned |

**Settled decisions:**
- **Strategy refinements** come from the journal and the feedback loop, one change at a time, each re-backtested.
- **`JournalEntry.outcome_pnl`** is the percent return net of costs on the levels you acted on. Journal rows add `counterfactual_pnl`, `expired` and `exit_reason`.
- **Design for crypto:** a shared BTC/ETH regime gate decides whether the environment favours longs, shorts or neither, and per-asset signals time the entry. Silver stands alone. Correlated crypto positions count as one exposure.

**Signal research notes**, from how professional quant systems work:
- **Signal families worth adding:** on-chain flows, funding rates and open interest for crypto; real yields, DXY and the gold/silver ratio for silver.
- **Testing a signal:**
  - validate walk-forward;
  - never use data unknown at decision time;
  - correct for multiple testing (a new factor should clear t ≈ 3, not 2);
  - treat 10–30 historical events as "worth monitoring", never "proven".
- **Combining signals:** use near-equal weights on z-scores, because optimized weights overfit. Uncorrelated signals add more than many correlated ones.

## For contributors (including other Claude sessions)

Read this README, then `git log`, then `src/orbit/core/types.py`, then `web/README.md` if you're touching the UI or API. Keep this README the single source of truth: update it in place when something changes.
