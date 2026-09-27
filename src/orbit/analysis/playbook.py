"""Assemble and persist the per-asset transit playbook.

Order of operations for one run:

1. Detect every transit event from the stored ephemeris (past and upcoming).
2. Write the hypothesis list to data/analysis/hypotheses.json *before* any
   test runs, and append this run to runs.jsonl. Re-running on the same data
   is another look at it; the run count is kept so that's visible.
3. Per asset: label outcomes per horizon, then for every pattern and horizon
   with at least MIN_OCCURRENCES occurrences, test BIG_UP / BIG_DOWN /
   SIDEWAYS rates against the circular-shift null.
4. Benjamini-Hochberg across each family (asset x patterns, asset x
   chop-states) and label every result.
5. Second pass: occurrence context and exceptions (needs every label).
6. The chop track (sideways.py).
7. Persist: {ASSET}.json per asset, events.json, meta.json.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable

import numpy as np

from orbit.config.settings import (
    BIG_MOVE_PERCENTILE,
    DATA_DIR,
    FDR_MODERATE,
    FDR_STRONG,
    INCLUDE_MOON,
    MIN_OCCURRENCES,
    MIN_SHIFT_GAP_DAYS,
    PLAYBOOK_HORIZONS,
    SIDEWAYS_DISPLACEMENT_PERCENTILE,
    SIDEWAYS_HORIZONS,
    SIDEWAYS_MIN_RANGE_PERCENTILE,
    STRONG_MIN_OCCURRENCES,
    TIMEFRAME,
    TIMING_HORIZONS_HOURS,
    TIMING_MAX_WINDOW_DAYS,
    TIMING_MIN_SHIFT_GAP_HOURS,
)
from orbit.core.types import (
    Asset,
    AssetPlaybook,
    ConfidenceLabel,
    Outcome,
    PatternHorizonStat,
    PatternOccurrence,
    PatternResult,
    PlaybookRunMeta,
    SidewaysStateResult,
    SpeedClass,
    TimingHorizonStat,
    TransitEvent,
)
from orbit.data.storage import load_candles
from orbit.features.arrays import rolling_mean, true_range
from orbit.features.regime import regime_gate_by_day, trend_values
from orbit.analysis import confidence, timing
from orbit.analysis.exact_times import refine
from orbit.analysis.exceptions import annotate, regime_per_bar, volatility_percentiles
from orbit.analysis.outcomes import BIG_DOWN, BIG_UP, CODE_TO_OUTCOME, SIDEWAYS, UNDEFINED, HorizonOutcomes, bar_index_for, label_outcomes
from orbit.analysis.patterns import Pattern, build_patterns
from orbit.analysis.series import PriceSeries, day64, load_planet_series, load_price_series
from orbit.analysis.sideways import state_masks, test_states
from orbit.analysis.significance import Spectrum, benjamini_hochberg, hypergeom_sf, shift_null_counts, shift_p_value
from orbit.analysis.transit_events import detect_all

ANALYSIS_DIR = DATA_DIR / "analysis"
EXACT_SINCE = datetime(2000, 1, 1, tzinfo=timezone.utc)  # exact moments computed from here (all price history is later)
ALL_ASSETS = [Asset.BTC, Asset.ETH, Asset.SOL, Asset.SILVER]
TARGETS = {BIG_UP: "big_up", BIG_DOWN: "big_down", SIDEWAYS: "sideways"}
DESCRIBE = {Outcome.BIG_UP: "a big up-move", Outcome.BIG_DOWN: "a big down-move", Outcome.SIDEWAYS: "a sideways stretch"}


# ---------------------------------------------------------------- per asset


def _regime_context(asset: Asset, series: PriceSeries) -> tuple[dict, str]:
    """{day: +1/-1/0} and its scope: the shared gate for crypto, own trend for silver."""
    if asset == Asset.SILVER:
        trend = trend_values(series.close)
        return {d: float(v) for d, v in zip(series.dates, trend) if not np.isnan(v)}, "OWN"
    btc, eth = load_candles(Asset.BTC, TIMEFRAME), load_candles(Asset.ETH, TIMEFRAME)
    return {day64(d): v for d, v in regime_gate_by_day(btc, eth).items()}, "SHARED"


def _pattern_indices(pattern: Pattern, series: PriceSeries) -> list[tuple[TransitEvent, int]]:
    out, seen = [], set()
    for e in pattern.events:
        i = bar_index_for(series.dates, day64(e.date))
        if i is not None and i not in seen:
            seen.add(i)
            out.append((e, i))
    return out


def _stat(o: HorizonOutcomes, rel: np.ndarray, cls, **horizon):
    codes = o.valid_codes[rel]
    fwd = o.forward_return[o.start : o.end][rel]
    n = len(rel)
    rate = (lambda c: float(np.mean(codes == c)) if n else 0.0)
    return cls(
        **horizon,
        n=n,
        big_up_rate=rate(BIG_UP),
        big_down_rate=rate(BIG_DOWN),
        sideways_rate=rate(SIDEWAYS),
        mean_return=float(fwd.mean()) if n else 0.0,
        median_return=float(np.median(fwd)) if n else 0.0,
        win_rate=float(np.mean(fwd > 0)) if n else 0.0,
        base_big_up_rate=o.base_rate(BIG_UP),
        base_big_down_rate=o.base_rate(BIG_DOWN),
        base_sideways_rate=o.base_rate(SIDEWAYS),
    )


def _target(o: HorizonOutcomes, code: int) -> tuple[np.ndarray, Spectrum]:
    """A 0/1 outcome series and its transform, shared by every pattern's tests."""
    y = (o.valid_codes == code).astype(float)
    return y, Spectrum(y)


def _horizon_tests(outcomes, targets, bars, horizons, cls, field, min_gap):
    """Stats per horizon and, where there are enough occurrences, one-sided
    circular-shift tests of each target. Returns (stats, [(horizon, target, p)])."""
    stats, tests = [], []
    for h in horizons:
        o = outcomes[h]
        rel = bars[(bars >= o.start) & (bars < o.end)] - o.start
        stat = _stat(o, rel, cls, **{field: h})
        if stat.n >= MIN_OCCURRENCES:
            L = o.end - o.start
            ind = np.zeros(L)
            ind[rel] = 1.0
            ind_spec = Spectrum(ind)  # transformed once, reused for all three targets
            best_uniform = None
            for t in TARGETS:
                y, y_spec = targets[h][t]
                hits = int(y[rel].sum())
                pval = shift_p_value(hits, shift_null_counts(y_spec, ind_spec, min_gap))
                setattr(stat, f"p_{TARGETS[t]}", pval)
                tests.append((h, t, pval))
                pu = hypergeom_sf(hits, L, int(y.sum()), stat.n)
                best_uniform = pu if best_uniform is None else min(best_uniform, pu)
            stat.p_uniform_best = best_uniform
        stats.append(stat)
    return stats, tests


def _rate(stat, target: int) -> tuple[float, float]:
    name = TARGETS[target]
    return getattr(stat, f"{name}_rate"), getattr(stat, f"base_{name}_rate")


def _headline(stats, horizon_of):
    """(label, score, stat, target) for the best-evidenced tested direction (lowest q,
    then p); for untested patterns, the most lopsided outcome at the horizon with the most data."""
    candidates = []
    for s in stats:
        for t, name in TARGETS.items():
            pv, qv = getattr(s, f"p_{name}"), getattr(s, f"q_{name}")
            if pv is not None and qv is not None:
                rate, base = _rate(s, t)
                candidates.append(((qv, pv, -confidence.lift(rate, base)), s, t))
    if candidates:
        _, s, t = min(candidates, key=lambda c: c[0])
        rate, base = _rate(s, t)
        pv, qv = getattr(s, f"p_{TARGETS[t]}"), getattr(s, f"q_{TARGETS[t]}")
        return confidence.label(s.n, rate, base, pv, qv), confidence.score(s.n, rate, base, pv, qv), s, t
    usable = [s for s in stats if s.n > 0]
    if not usable:
        return ConfidenceLabel.INSUFFICIENT_DATA, 0, None, None
    s = max(usable, key=lambda x: (x.n, -horizon_of(x)))
    t = max(TARGETS, key=lambda tt: confidence.lift(*_rate(s, tt)) if _rate(s, tt)[1] > 0 else 0)
    return ConfidenceLabel.INSUFFICIENT_DATA, 0, s, t


VERDICT = {
    ConfidenceLabel.STRONG: "Survives multiple-testing correction with a large effect.",
    ConfidenceLabel.MODERATE: "Survives multiple-testing correction at the looser threshold.",
    ConfidenceLabel.WEAK: "Nominally significant, but does not survive multiple-testing correction.",
    ConfidenceLabel.NONE: "No better than chance.",
}


def _describe(stat, target: int, label: ConfidenceLabel, unit: str, horizon: int) -> str:
    rate, base = _rate(stat, target)
    hits = round(rate * stat.n)
    body = f"{hits} of {stat.n} occurrences were followed by {DESCRIBE[CODE_TO_OUTCOME[target]]} within {horizon} {unit} ({rate:.0%}, vs {base:.0%} normally)"
    if label == ConfidenceLabel.INSUFFICIENT_DATA:
        return f"{body}. Too few occurrences to judge; treat as anecdote."
    q = getattr(stat, f"q_{TARGETS[target]}")
    return f"{body}. q = {q:.3f}. {VERDICT[label]}"


def _summary(p: Pattern, result: PatternResult, stat, target) -> str:
    if result.n_events == 0:
        return f"{p.description}: never happened during this asset's price history."
    if stat is None:
        return f"{p.description}: {result.n_events} occurrences, none with a completed forward window yet."
    return f"{p.description}: " + _describe(stat, target, result.label, "days", stat.horizon_days)


def _daily_atr_fraction(series: PriceSeries) -> np.ndarray:
    atr = rolling_mean(true_range(series.high, series.low, series.close), 14)
    return atr / series.close


def build_asset_playbook(asset, series, patterns, events, planets, now, hourly: PriceSeries | None = None) -> tuple[AssetPlaybook, dict[str, int]]:
    horizons = sorted({h for hs in PLAYBOOK_HORIZONS.values() for h in hs} | set(SIDEWAYS_HORIZONS))
    outcomes = {h: label_outcomes(series, h) for h in horizons}
    targets = {h: {t: _target(o, t) for t in TARGETS} for h, o in outcomes.items()}
    ctx = timing.build_context(hourly, tuple(TARGETS)) if hourly is not None else None
    if ctx is not None:
        ctx.targets = {h: {t: _target(o, t) for t in TARGETS} for h, o in ctx.outcomes.items()}

    results: dict[str, PatternResult] = {}
    indexed: dict[str, list[tuple[TransitEvent, int]]] = {}
    hourly_indexed: dict[str, list[tuple[TransitEvent, int]]] = {}
    tests: list[tuple[str, str, str, int, int, float]] = []  # (family, pattern_id, kind, horizon, target, p)

    for p in patterns:
        pairs = _pattern_indices(p, series)
        indexed[p.pattern_id] = pairs
        stats, found = _horizon_tests(outcomes, targets, np.array([i for _, i in pairs], dtype=int),
                                      PLAYBOOK_HORIZONS[p.speed_class.value], PatternHorizonStat, "horizon_days", MIN_SHIFT_GAP_DAYS)
        family = f"{asset.value}:{p.family_key}"
        tests += [(family, p.pattern_id, "daily", h, t, pv) for h, t, pv in found]
        timing_stats = []
        if ctx is not None:
            hpairs = timing.event_bars(ctx, p.events)
            hourly_indexed[p.pattern_id] = hpairs
            timing_stats, found = _horizon_tests(ctx.outcomes, ctx.targets, np.array([i for _, i in hpairs], dtype=int),
                                                 TIMING_HORIZONS_HOURS, TimingHorizonStat, "horizon_hours", TIMING_MIN_SHIFT_GAP_HOURS)
            tests += [(f"{asset.value}:TIMING", p.pattern_id, "timing", h, t, pv) for h, t, pv in found]
        results[p.pattern_id] = PatternResult(
            pattern_id=p.pattern_id, description=p.description, planet=p.planet, event_type=p.event_type,
            sign=p.sign, speed_class=p.speed_class, family=family, n_events=len(pairs), horizons=stats,
            label=ConfidenceLabel.INSUFFICIENT_DATA, score=0, summary="", timing=timing_stats,
        )

    # FDR per family (daily patterns, and hourly timing, corrected separately per asset).
    families: dict[str, list[int]] = {}
    for k, t in enumerate(tests):
        families.setdefault(t[0], []).append(k)
    for ks in families.values():
        for k, q in zip(ks, benjamini_hochberg([tests[k][5] for k in ks])):
            _, pid, kind, h, t, _ = tests[k]
            if kind == "daily":
                stat = next(s for s in results[pid].horizons if s.horizon_days == h)
            else:
                stat = next(s for s in results[pid].timing if s.horizon_hours == h)
            setattr(stat, f"q_{TARGETS[t]}", q)

    atr_fraction = _daily_atr_fraction(series)
    for p in patterns:
        r = results[p.pattern_id]
        r.label, r.score, s, t = _headline(r.horizons, lambda x: x.horizon_days)
        if s is not None:
            r.headline_horizon, r.dominant_outcome = s.horizon_days, CODE_TO_OUTCOME[t]
        r.summary = _summary(p, r, s, t)
        if r.timing:
            r.timing_label, r.timing_score, ts, tt = _headline(r.timing, lambda x: x.horizon_hours)
            if ts is not None:
                r.timing_headline_hours, r.timing_dominant = ts.horizon_hours, CODE_TO_OUTCOME[tt]
                r.timing_summary = "From the exact moment: " + _describe(ts, tt, r.timing_label, "hours", ts.horizon_hours)

        # Occurrences (not stored for the Moon: thousands of rows, better read in aggregate).
        if p.speed_class == SpeedClass.LUNAR or r.headline_horizon is None:
            continue
        o = outcomes[r.headline_horizon]
        hourly_bar = {id(e): i for e, i in hourly_indexed.get(p.pattern_id, [])}
        moves = []
        for e, i in indexed[p.pattern_id]:
            defined = o.start <= i < o.end and o.codes[i] != UNDEFINED
            occ = PatternOccurrence(
                date=e.date,
                event=e,
                outcome=CODE_TO_OUTCOME[int(o.codes[i])] if defined else None,
                forward_return=float(o.forward_return[i]) if defined else None,
            )
            hi = hourly_bar.get(id(e))
            if ctx is not None and hi is not None:
                direction = {Outcome.BIG_UP: 1, Outcome.BIG_DOWN: -1}.get(r.dominant_outcome)
                if direction is None and occ.forward_return is not None:
                    direction = 1 if occ.forward_return >= 0 else -1
                window = 24 * min(r.headline_horizon, TIMING_MAX_WINDOW_DAYS)
                frac = float(atr_fraction[i]) if not np.isnan(atr_fraction[i]) else None
                metrics = timing.path_metrics(ctx.series, hi, direction, window, frac)
                for k, v in metrics.items():
                    setattr(occ, k, v)
                if occ.hours_to_move is not None:
                    moves.append(occ.hours_to_move)
            r.occurrences.append(occ)
        if moves:
            r.median_hours_to_move = float(np.median(moves))
            note = f" Moves of a normal day's range typically began {r.median_hours_to_move:.0f} hours after the exact moment ({len(moves)} occurrences)."
            r.timing_summary = (r.timing_summary + note) if r.timing_summary else note.strip()

    # Second pass: context and exceptions.
    regime_by_day, scope = _regime_context(asset, series)
    event_bars = [(e, i) for e in events if e.planet.value != "MOON" for i in [bar_index_for(series.dates, day64(e.date))] if i is not None]
    annotate(results, series, event_bars, regime_per_bar(series, regime_by_day), scope, volatility_percentiles(series))

    # Chop track.
    masks = state_masks(series, planets)
    side_tests = [st for h in SIDEWAYS_HORIZONS for st in test_states(outcomes[h], masks)]
    tested = [k for k, st in enumerate(side_tests) if st.p is not None]
    qmap = dict(zip(tested, benjamini_hochberg([side_tests[k].p for k in tested])))
    sideways = [
        SidewaysStateResult(
            state_id=st.state_id,
            description=st.description,
            horizon_days=st.horizon,
            days_in_state=st.days,
            episodes=st.episodes,
            sideways_rate_in_state=st.rate,
            base_sideways_rate=st.base,
            p_value=st.p,
            q_value=qmap.get(k),
            label=confidence.label(st.episodes, st.rate, st.base, st.p, qmap.get(k)),
            score=confidence.score(st.episodes, st.rate, st.base, st.p, qmap.get(k)),
        )
        for k, st in enumerate(side_tests)
    ]
    counts = {fam: len(ks) for fam, ks in families.items()}
    counts[f"{asset.value}:SIDEWAYS"] = len(tested)

    to_dt = lambda d: datetime.fromisoformat(str(d)).replace(tzinfo=timezone.utc)
    playbook = AssetPlaybook(
        asset=asset,
        generated_at=now,
        history_start=to_dt(series.dates[0]),
        history_end=to_dt(series.dates[-1]),
        bars=len(series),
        hourly_start=to_dt(ctx.series.dates[0]) if ctx else None,
        hourly_bars=len(ctx.series) if ctx else 0,
        patterns=sorted(results.values(), key=lambda r: (-confidence.RANK[r.label], -r.score, -confidence.RANK[r.timing_label], -r.n_events)),
        sideways=sorted(sideways, key=lambda s: (-confidence.RANK[s.label], -s.score)),
    )
    return playbook, counts


# ---------------------------------------------------------------- whole run


def _parameters() -> dict:
    return {
        "big_move_percentile": BIG_MOVE_PERCENTILE,
        "sideways_displacement_percentile": SIDEWAYS_DISPLACEMENT_PERCENTILE,
        "sideways_min_range_percentile": SIDEWAYS_MIN_RANGE_PERCENTILE,
        "min_occurrences": MIN_OCCURRENCES,
        "strong_min_occurrences": STRONG_MIN_OCCURRENCES,
        "fdr_strong": FDR_STRONG,
        "fdr_moderate": FDR_MODERATE,
        "min_shift_gap_days": MIN_SHIFT_GAP_DAYS,
        "horizons_lunar": PLAYBOOK_HORIZONS["LUNAR"],
        "horizons_fast": PLAYBOOK_HORIZONS["FAST"],
        "horizons_slow": PLAYBOOK_HORIZONS["SLOW"],
        "timing_horizons_hours": TIMING_HORIZONS_HOURS,
        "timing_min_shift_gap_hours": TIMING_MIN_SHIFT_GAP_HOURS,
        "sideways_horizons": SIDEWAYS_HORIZONS,
        "include_moon": INCLUDE_MOON,
        "null": "circular shift of the event calendar (FFT); negative-binomial tail below shift resolution; exact hypergeometric uniform-date check",
        "thresholds": "full-history percentiles (retrospective only; not for live use)",
    }


def load_events() -> list[TransitEvent]:
    """Every transit from the stored ephemeris, with exact moments from EXACT_SINCE on."""
    planets = load_planet_series()
    if not planets:
        raise RuntimeError("no ephemeris stored; run scripts/fetch_ephemeris.py first")
    return refine(detect_all(planets), since=EXACT_SINCE)


def build_all(
    assets: list[Asset] = ALL_ASSETS,
    progress: Callable[[str, float], None] | None = None,
    events: list[TransitEvent] | None = None,
) -> PlaybookRunMeta:
    """Rebuild every asset's playbook. `progress(step, fraction)` is called as it goes."""
    say = progress or (lambda step, frac: None)
    now = datetime.now(timezone.utc)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    say("Loading ephemeris and computing exact transit moments", 0.02)
    planets = load_planet_series()
    if events is None:
        events = load_events()
    patterns = build_patterns(events, INCLUDE_MOON)

    # Pre-registration record and run log, written before any test.
    (ANALYSIS_DIR / "hypotheses.json").write_text(
        json.dumps(
            {
                "written_at": now.isoformat(),
                "patterns": [p.pattern_id for p in patterns],
                "targets": list(TARGETS.values()),
                "horizons": PLAYBOOK_HORIZONS,
                "timing_horizons_hours": TIMING_HORIZONS_HOURS,
                "tested_only_if_occurrences_at_least": MIN_OCCURRENCES,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    runs_path = ANALYSIS_DIR / "runs.jsonl"
    with runs_path.open("a") as f:
        f.write(json.dumps({"started_at": now.isoformat()}) + "\n")

    (ANALYSIS_DIR / "events.json").write_text(json.dumps([e.model_dump(mode="json") for e in events]), encoding="utf-8")

    tests_by_family: dict[str, int] = {}
    asset_meta: dict[str, dict] = {}
    for k, asset in enumerate(assets):
        say(f"Testing {asset.value}: daily and hourly patterns", 0.05 + 0.9 * k / len(assets))
        series = load_price_series(asset)
        if len(series) < 300:
            asset_meta[asset.value] = {"skipped": "not enough stored price history"}
            continue
        hourly = load_price_series(asset, timeframe="1h")
        playbook, counts = build_asset_playbook(asset, series, patterns, events, planets, now, hourly if len(hourly) else None)
        tests_by_family.update(counts)
        (ANALYSIS_DIR / f"{asset.value}.json").write_text(playbook.model_dump_json(), encoding="utf-8")
        labels: dict[str, int] = {}
        timing_labels: dict[str, int] = {}
        for r in playbook.patterns:
            labels[r.label.value] = labels.get(r.label.value, 0) + 1
            if r.timing:
                timing_labels[r.timing_label.value] = timing_labels.get(r.timing_label.value, 0) + 1
        asset_meta[asset.value] = {
            "history_start": playbook.history_start.date().isoformat(),
            "history_end": playbook.history_end.date().isoformat(),
            "bars": playbook.bars,
            "hourly_bars": playbook.hourly_bars,
            **{f"patterns_{k}": v for k, v in labels.items()},
            **{f"timing_{k}": v for k, v in timing_labels.items()},
        }

    meta = PlaybookRunMeta(
        generated_at=now,
        parameters={**_parameters(), "runs_so_far": sum(1 for _ in runs_path.open())},
        tests_by_family=tests_by_family,
        total_tests=sum(tests_by_family.values()),
        assets=asset_meta,
    )
    (ANALYSIS_DIR / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    say("Playbook written", 0.96)
    return meta
