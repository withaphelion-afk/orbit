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
    TransitEvent,
)
from orbit.data.storage import load_candles
from orbit.features.regime import regime_gate_by_day, trend_values
from orbit.analysis import confidence
from orbit.analysis.exceptions import annotate, regime_per_bar, volatility_percentiles
from orbit.analysis.outcomes import BIG_DOWN, BIG_UP, CODE_TO_OUTCOME, SIDEWAYS, UNDEFINED, HorizonOutcomes, bar_index_for, label_outcomes
from orbit.analysis.patterns import Pattern, build_patterns
from orbit.analysis.series import PriceSeries, day64, load_planet_series, load_price_series
from orbit.analysis.sideways import state_masks, test_states
from orbit.analysis.significance import benjamini_hochberg, hypergeom_sf, shift_null_counts, shift_p_value
from orbit.analysis.transit_events import detect_all

ANALYSIS_DIR = DATA_DIR / "analysis"
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


def _horizon_stat(o: HorizonOutcomes, rel: np.ndarray) -> PatternHorizonStat:
    codes = o.valid_codes[rel]
    fwd = o.forward_return[o.start : o.end][rel]
    n = len(rel)
    rate = (lambda c: float(np.mean(codes == c)) if n else 0.0)
    return PatternHorizonStat(
        horizon_days=o.horizon,
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


def _rate(stat: PatternHorizonStat, target: int) -> tuple[float, float]:
    name = TARGETS[target]
    return getattr(stat, f"{name}_rate"), getattr(stat, f"base_{name}_rate")


def _summary(p: Pattern, result: PatternResult) -> str:
    if result.n_events == 0:
        return f"{p.description}: never happened during this asset's price history."
    head = next((h for h in result.horizons if h.horizon_days == result.headline_horizon), None)
    if head is None or result.dominant_outcome is None:
        return f"{p.description}: {result.n_events} occurrences, none with a completed forward window yet."
    target = {Outcome.BIG_UP: BIG_UP, Outcome.BIG_DOWN: BIG_DOWN, Outcome.SIDEWAYS: SIDEWAYS}[result.dominant_outcome]
    rate, base = _rate(head, target)
    hits = round(rate * head.n)
    what = DESCRIBE[result.dominant_outcome]
    body = (
        f"{hits} of {head.n} occurrences were followed by {what} within {head.horizon_days} bars "
        f"({rate:.0%}, vs {base:.0%} on a typical day)"
    )
    if result.label == ConfidenceLabel.INSUFFICIENT_DATA:
        return f"{p.description}: {body}. Too few occurrences to judge; treat as anecdote."
    q = getattr(head, f"q_{TARGETS[target]}")
    verdict = {
        ConfidenceLabel.STRONG: "Survives multiple-testing correction with a large effect.",
        ConfidenceLabel.MODERATE: "Survives multiple-testing correction at the looser threshold.",
        ConfidenceLabel.WEAK: "Nominally significant, but does not survive multiple-testing correction.",
        ConfidenceLabel.NONE: "No better than chance.",
    }[result.label]
    return f"{p.description}: {body}. q = {q:.3f}. {verdict}"


def build_asset_playbook(asset, series, patterns, events, planets, now) -> tuple[AssetPlaybook, dict[str, int]]:
    horizons = sorted({h for hs in PLAYBOOK_HORIZONS.values() for h in hs} | set(SIDEWAYS_HORIZONS))
    outcomes = {h: label_outcomes(series, h) for h in horizons}
    targets = {h: {t: (o.valid_codes == t).astype(float) for t in TARGETS} for h, o in outcomes.items()}

    results: dict[str, PatternResult] = {}
    indexed: dict[str, list[tuple[TransitEvent, int]]] = {}
    tests: list[tuple[str, str, int, int, float]] = []  # (family, pattern_id, horizon, target, p)

    for p in patterns:
        family = f"{asset.value}:{p.family_key}"
        pairs = _pattern_indices(p, series)
        indexed[p.pattern_id] = pairs
        bars = np.array([i for _, i in pairs], dtype=int)
        stats = []
        for h in PLAYBOOK_HORIZONS[p.speed_class.value]:
            o = outcomes[h]
            rel = bars[(bars >= o.start) & (bars < o.end)] - o.start
            stat = _horizon_stat(o, rel)
            if stat.n >= MIN_OCCURRENCES:
                L = o.end - o.start
                ind = np.zeros(L)
                ind[rel] = 1.0
                best_uniform = None
                for t in TARGETS:
                    y = targets[h][t]
                    hits = int(y[rel].sum())
                    pval = shift_p_value(hits, shift_null_counts(y, ind, MIN_SHIFT_GAP_DAYS))
                    setattr(stat, f"p_{TARGETS[t]}", pval)
                    tests.append((family, p.pattern_id, h, t, pval))
                    pu = hypergeom_sf(hits, L, int(y.sum()), stat.n)
                    best_uniform = pu if best_uniform is None else min(best_uniform, pu)
                stat.p_uniform_best = best_uniform
            stats.append(stat)
        results[p.pattern_id] = PatternResult(
            pattern_id=p.pattern_id,
            description=p.description,
            planet=p.planet,
            event_type=p.event_type,
            sign=p.sign,
            speed_class=p.speed_class,
            family=family,
            n_events=len(pairs),
            horizons=stats,
            label=ConfidenceLabel.INSUFFICIENT_DATA,
            score=0,
            summary="",
        )

    # FDR per family.
    families: dict[str, list[int]] = {}
    for k, t in enumerate(tests):
        families.setdefault(t[0], []).append(k)
    for fam, ks in families.items():
        qs = benjamini_hochberg([tests[k][4] for k in ks])
        for k, q in zip(ks, qs):
            _, pid, h, t, _ = tests[k]
            stat = next(s for s in results[pid].horizons if s.horizon_days == h)
            setattr(stat, f"q_{TARGETS[t]}", q)

    # Label: headline = the best-evidenced (lowest q, then p) tested direction.
    for p in patterns:
        r = results[p.pattern_id]
        candidates = []
        for s in r.horizons:
            for t, name in TARGETS.items():
                pv, qv = getattr(s, f"p_{name}"), getattr(s, f"q_{name}")
                rate, base = _rate(s, t)
                if pv is not None and qv is not None:
                    candidates.append(((qv, pv, -confidence.lift(rate, base)), s, t))
        if candidates:
            _, s, t = min(candidates, key=lambda c: c[0])
            rate, base = _rate(s, t)
            pv, qv = getattr(s, f"p_{TARGETS[t]}"), getattr(s, f"q_{TARGETS[t]}")
            r.label = confidence.label(s.n, rate, base, pv, qv)
            r.score = confidence.score(s.n, rate, base, pv, qv)
        else:
            # Untested: describe the most lopsided outcome at the horizon with the most data.
            usable = [s for s in r.horizons if s.n > 0]
            if not usable:
                r.summary = _summary(p, r)
                continue
            s = max(usable, key=lambda x: (x.n, -x.horizon_days))
            t = max(TARGETS, key=lambda tt: confidence.lift(*_rate(s, tt)) if _rate(s, tt)[1] > 0 else 0)
        r.headline_horizon = s.horizon_days
        r.dominant_outcome = CODE_TO_OUTCOME[t]
        r.summary = _summary(p, r)

        # Occurrences (not stored for the Moon: thousands of rows, better read in aggregate).
        if p.speed_class != SpeedClass.LUNAR:
            o = outcomes[r.headline_horizon]
            for e, i in indexed[p.pattern_id]:
                defined = o.start <= i < o.end and o.codes[i] != UNDEFINED
                r.occurrences.append(
                    PatternOccurrence(
                        date=e.date,
                        event=e,
                        outcome=CODE_TO_OUTCOME[int(o.codes[i])] if defined else None,
                        forward_return=float(o.forward_return[i]) if defined else None,
                    )
                )

    # Second pass: context and exceptions.
    regime_by_day, scope = _regime_context(asset, series)
    event_bars = [(e, i) for e in events if e.planet.value != "MOON" for i in [bar_index_for(series.dates, day64(e.date))] if i is not None]
    annotate(results, series, event_bars, regime_per_bar(series, regime_by_day), scope, volatility_percentiles(series))

    # Chop track.
    masks = state_masks(series, planets)
    side_tests = [st for h in SIDEWAYS_HORIZONS for st in test_states(outcomes[h], masks)]
    tested = [k for k, st in enumerate(side_tests) if st.p is not None]
    qs = benjamini_hochberg([side_tests[k].p for k in tested])
    qmap = dict(zip(tested, qs))
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

    playbook = AssetPlaybook(
        asset=asset,
        generated_at=now,
        history_start=datetime.fromisoformat(str(series.dates[0])).replace(tzinfo=timezone.utc),
        history_end=datetime.fromisoformat(str(series.dates[-1])).replace(tzinfo=timezone.utc),
        bars=len(series),
        patterns=sorted(results.values(), key=lambda r: (-confidence.RANK[r.label], -r.score, -r.n_events)),
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
        "sideways_horizons": SIDEWAYS_HORIZONS,
        "include_moon": INCLUDE_MOON,
        "null": "circular shift of the event calendar (FFT); negative-binomial tail below shift resolution; exact hypergeometric uniform-date check",
        "thresholds": "full-history percentiles (retrospective only; not for live use)",
    }


def build_all(assets: list[Asset] = ALL_ASSETS) -> PlaybookRunMeta:
    now = datetime.now(timezone.utc)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    planets = load_planet_series()
    if not planets:
        raise RuntimeError("no ephemeris stored; run scripts/fetch_ephemeris.py first")
    events = detect_all(planets)
    patterns = build_patterns(events, INCLUDE_MOON)

    # Pre-registration record and run log, written before any test.
    (ANALYSIS_DIR / "hypotheses.json").write_text(
        json.dumps(
            {
                "written_at": now.isoformat(),
                "patterns": [p.pattern_id for p in patterns],
                "targets": list(TARGETS.values()),
                "horizons": PLAYBOOK_HORIZONS,
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
    for asset in assets:
        series = load_price_series(asset)
        if len(series) < 300:
            asset_meta[asset.value] = {"skipped": "not enough stored price history"}
            continue
        playbook, counts = build_asset_playbook(asset, series, patterns, events, planets, now)
        tests_by_family.update(counts)
        (ANALYSIS_DIR / f"{asset.value}.json").write_text(playbook.model_dump_json(), encoding="utf-8")
        labels: dict[str, int] = {}
        for r in playbook.patterns:
            labels[r.label.value] = labels.get(r.label.value, 0) + 1
        asset_meta[asset.value] = {
            "history_start": playbook.history_start.date().isoformat(),
            "history_end": playbook.history_end.date().isoformat(),
            "bars": playbook.bars,
            **{f"patterns_{k}": v for k, v in labels.items()},
        }

    meta = PlaybookRunMeta(
        generated_at=now,
        parameters={**_parameters(), "runs_so_far": sum(1 for _ in runs_path.open())},
        tests_by_family=tests_by_family,
        total_tests=sum(tests_by_family.values()),
        assets=asset_meta,
    )
    (ANALYSIS_DIR / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    return meta
