import json
import warnings
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from orbit.analysis import projection_log, projections
from orbit.analysis.outcomes import CODE_TO_OUTCOME, label_outcomes
from orbit.analysis.projections import Conditions, build_projections, project, wilson_interval, window_end
from orbit.analysis.series import PriceSeries
from orbit.core.types import (
    Asset,
    AssetPlaybook,
    ConfidenceLabel,
    LoggedProjection,
    Outcome,
    PatternHorizonStat,
    PatternOccurrence,
    PatternResult,
    Planet,
    SpeedClass,
    TransitEvent,
    TransitEventType,
)

L = ConfidenceLabel
NOW = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)  # a Saturday


def _event(at: datetime, planet=Planet.MARS, to_state="Mesha", event_type=TransitEventType.INGRESS) -> TransitEvent:
    return TransitEvent(planet=planet, event_type=event_type, date=at.replace(hour=0, minute=0, second=0, microsecond=0),
                        exact_time=at, from_state="", to_state=to_state, label=f"{planet.value} {to_state}")


def _stat(h: int, n: int = 30, outcome: Outcome = Outcome.BIG_UP, rate: float = 0.4, base: float = 0.15, q: float = 0.03) -> PatternHorizonStat:
    rates = {"big_up_rate": 0.1, "big_down_rate": 0.1, "sideways_rate": 0.2}
    bases = {"base_big_up_rate": 0.15, "base_big_down_rate": 0.15, "base_sideways_rate": 0.25}
    name = projections.RATE[outcome]
    rates[f"{name}_rate"], bases[f"base_{name}_rate"] = rate, base
    return PatternHorizonStat(horizon_days=h, n=n, mean_return=0.02, median_return=0.01, win_rate=0.6, **rates, **bases,
                              **{f"q_{name}": q, f"p_{name}": q / 2})


def _result(pid: str, label: L, score: int = 20, outcome: Outcome = Outcome.BIG_UP, h: int = 5, speed=SpeedClass.FAST,
            occurrences=(), **stat) -> PatternResult:
    horizons = [] if label == L.INSUFFICIENT_DATA else [_stat(h, outcome=outcome, **stat)]
    return PatternResult(
        pattern_id=pid, description=pid, planet=Planet.MARS, event_type=TransitEventType.INGRESS, speed_class=speed, family="PATTERNS",
        n_events=30, horizons=horizons, headline_horizon=h if horizons else None, dominant_outcome=outcome if horizons else None,
        label=label, score=score, summary="", occurrences=list(occurrences),
    )


def _playbook(asset: Asset, results: list[PatternResult]) -> AssetPlaybook:
    return AssetPlaybook(asset=asset, generated_at=NOW, history_start=NOW - timedelta(days=3000), history_end=NOW, bars=3000,
                         patterns=results, sideways=[])


# ---------------------------------------------------------------- building


def test_best_pattern_wins_by_label_then_score():
    e = _event(NOW + timedelta(days=2))  # belongs to MARS:RASHI and MARS:RASHI:Mesha
    pb = _playbook(Asset.BTC, [_result("MARS:RASHI", L.WEAK, score=90), _result("MARS:RASHI:Mesha", L.MODERATE, score=10)])
    [p] = build_projections([e], {Asset.BTC: pb}, NOW)
    assert p.pattern_id == "MARS:RASHI:Mesha" and p.trusted and p.label == L.MODERATE

    pb = _playbook(Asset.BTC, [_result("MARS:RASHI", L.WEAK, score=30), _result("MARS:RASHI:Mesha", L.WEAK, score=10)])
    [p] = build_projections([e], {Asset.BTC: pb}, NOW)
    assert p.pattern_id == "MARS:RASHI" and not p.trusted
    assert p.note.startswith("Unproven, not significant")


def test_only_upcoming_events_inside_the_window():
    pb = _playbook(Asset.BTC, [_result("MARS:RASHI", L.STRONG)])
    events = [_event(NOW - timedelta(hours=1)), _event(NOW + timedelta(days=1)), _event(NOW + timedelta(days=61))]
    rows = build_projections(events, {Asset.BTC: pb}, NOW)
    assert [r.window_start for r in rows] == [NOW + timedelta(days=1)]
    assert len(build_projections(events, {Asset.BTC: pb}, NOW, days_ahead=90)) == 2


def test_none_hidden_by_default_and_insufficient_data_never_shown():
    e = _event(NOW + timedelta(days=1))
    pb = _playbook(Asset.ETH, [_result("MARS:RASHI", L.NONE)])
    assert build_projections([e], {Asset.ETH: pb}, NOW) == []
    [p] = build_projections([e], {Asset.ETH: pb}, NOW, include_none=True)
    assert not p.trusted and "no better than chance" in p.note

    pb = _playbook(Asset.ETH, [_result("MARS:RASHI", L.INSUFFICIENT_DATA)])
    assert build_projections([e], {Asset.ETH: pb}, NOW, include_none=True) == []


def test_wilson_interval_known_values():
    lo, hi = wilson_interval(0.5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4) and hi == pytest.approx(0.7634, abs=1e-4)
    lo, hi = wilson_interval(0.0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.2775, abs=1e-4)


def test_rates_lift_and_calculation_fields():
    e = _event(NOW + timedelta(days=1))
    p = project(Asset.BTC, e, _result("MARS:RASHI", L.STRONG, outcome=Outcome.BIG_DOWN, h=10, rate=0.45, base=0.15, q=0.01, n=40))
    assert (p.outcome, p.horizon_days, p.n) == (Outcome.BIG_DOWN, 10, 40)
    assert p.hit_rate == 0.45 and p.base_rate == 0.15 and p.lift == pytest.approx(3.0) and p.q_value == 0.01
    assert (p.ci_low, p.ci_high) == wilson_interval(0.45, 40)
    assert "18 of 40" in p.note and "q = 0.010" in p.note
    zero_base = project(Asset.BTC, e, _result("MARS:RASHI", L.WEAK, rate=0.2, base=0.0))
    assert zero_base.lift is None


def test_overlapping_windows_group_and_flag_conflicts():
    up = _event(datetime(2026, 10, 5, 9, tzinfo=timezone.utc), planet=Planet.MARS, to_state="Mesha")
    down = _event(datetime(2026, 10, 8, 9, tzinfo=timezone.utc), planet=Planet.VENUS, to_state="Tula")
    later = _event(datetime(2026, 11, 20, 9, tzinfo=timezone.utc), planet=Planet.SUN, to_state="Dhanu")
    pb = _playbook(Asset.BTC, [
        _result("MARS:RASHI", L.MODERATE, h=5, outcome=Outcome.BIG_UP),
        _result("VENUS:RASHI", L.WEAK, h=5, outcome=Outcome.BIG_DOWN),
        _result("SUN:RASHI", L.WEAK, h=1, outcome=Outcome.BIG_UP),
    ])
    a, b, c = build_projections([up, down, later], {Asset.BTC: pb}, NOW)
    assert a.group_id == b.group_id != c.group_id
    assert a.conflict and b.conflict and not c.conflict

    # Groups hang off their first window and don't chain: c overlaps b but starts after a's window ends.
    pb = _playbook(Asset.BTC, [
        _result("MARS:RASHI", L.WEAK, h=1, outcome=Outcome.BIG_UP),
        _result("VENUS:RASHI", L.WEAK, h=5, outcome=Outcome.BIG_UP),
        _result("SUN:RASHI", L.WEAK, h=1, outcome=Outcome.BIG_DOWN),
    ])
    a = _event(datetime(2026, 10, 5, 9, tzinfo=timezone.utc), planet=Planet.MARS)
    b = _event(datetime(2026, 10, 6, 9, tzinfo=timezone.utc), planet=Planet.VENUS, to_state="Tula")
    c = _event(datetime(2026, 10, 9, 9, tzinfo=timezone.utc), planet=Planet.SUN, to_state="Dhanu")
    a, b, c = build_projections([a, b, c], {Asset.BTC: pb}, NOW)
    assert a.group_id == b.group_id == "BTC:2026-10-05" and c.group_id == "BTC:2026-10-09"
    assert not a.conflict and not c.conflict
    # Another asset's windows never join BTC's groups.
    eth = build_projections([_event(datetime(2026, 10, 5, 9, tzinfo=timezone.utc))], {Asset.ETH: _playbook(Asset.ETH, [_result("MARS:RASHI", L.WEAK)])}, NOW)
    assert eth[0].group_id == "ETH:2026-10-05"


def test_like_now_filters_by_regime_and_volatility():
    def occ(regime, vol, outcome):
        e = _event(datetime(2020, 1, 1, tzinfo=timezone.utc))
        return PatternOccurrence(date=e.date, event=e, outcome=outcome, forward_return=0.0, regime=regime, volatility_percentile=vol)

    occurrences = [
        occ("BULL", 0.6, Outcome.BIG_UP),
        occ("BULL", 0.35, Outcome.BIG_DOWN),
        occ("BULL", 0.75, Outcome.BIG_UP),  # 0.25 away: outside the band
        occ("BEAR", 0.5, Outcome.BIG_UP),  # other regime
        occ("BULL", 0.5, None),  # outcome not known yet
    ]
    e = _event(NOW + timedelta(days=1))
    p = project(Asset.BTC, e, _result("MARS:RASHI", L.WEAK, occurrences=occurrences), Conditions("BULL", 0.5))
    assert (p.like_now.n, p.like_now.matches, p.like_now.share) == (2, 1, 0.5)
    assert project(Asset.BTC, e, _result("MARS:RASHI", L.WEAK, occurrences=occurrences), Conditions("CHOPPY", 0.5)).like_now is None
    lunar = _result("MARS:RASHI", L.WEAK, occurrences=occurrences, speed=SpeedClass.LUNAR)
    assert project(Asset.BTC, e, lunar, Conditions("BULL", 0.5)).like_now is None


def test_silver_window_counts_weekdays_only():
    friday = datetime(2026, 10, 9, tzinfo=timezone.utc)
    assert window_end(Asset.SILVER, friday, 5) == datetime(2026, 10, 16, tzinfo=timezone.utc)
    assert window_end(Asset.BTC, friday, 5) == datetime(2026, 10, 14, tzinfo=timezone.utc)
    # A Saturday event belongs to Monday's bar; one bar later is Tuesday.
    assert window_end(Asset.SILVER, friday + timedelta(days=1), 1) == datetime(2026, 10, 13, tzinfo=timezone.utc)


# ---------------------------------------------------------------- forward track record


def _walk(n: int, start: datetime, seed: int = 3) -> PriceSeries:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, n)))
    dates = np.datetime64(start.replace(tzinfo=None), "D") + np.arange(n).astype("timedelta64[D]")
    return PriceSeries(Asset.BTC, dates, close.copy(), close * 1.01, close * 0.99, close)


def _head(s: PriceSeries, k: int) -> PriceSeries:
    return PriceSeries(s.asset, s.dates[:k], s.open[:k], s.high[:k], s.low[:k], s.close[:k])


def test_record_is_idempotent_and_never_rewrites_a_prediction(tmp_path):
    path = tmp_path / "log.json"
    p = project(Asset.BTC, _event(NOW + timedelta(days=1)), _result("MARS:RASHI", L.WEAK, rate=0.3))
    assert projection_log.record([p], NOW, path) == 1
    relabelled = p.model_copy(update={"label": L.STRONG, "hit_rate": 0.9, "note": "changed"})
    assert projection_log.record([relabelled, p], NOW + timedelta(days=1), path) == 0
    [row] = projection_log.load(path)
    assert row.projection == p and row.recorded_at == NOW


def test_grade_waits_for_the_full_window_and_uses_label_outcomes(tmp_path):
    path = tmp_path / "log.json"
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    full = _walk(400, start)
    k, h = 300, 5
    event_day = start + timedelta(days=k)
    p = project(Asset.BTC, _event(event_day + timedelta(hours=10)), _result("MARS:RASHI", L.WEAK, h=h))
    projection_log.record([p], event_day - timedelta(days=1), path)

    # Stored bars end one bar short of the window: nothing is graded.
    now = start + timedelta(days=k + h)  # bar k+h is today's, still forming, so not usable
    assert projection_log.grade(now, path, series_for=lambda a: full) == []
    assert projection_log.load(path)[0].graded_at is None

    # The window's last bar has closed: graded exactly as label_outcomes labels it on bars up to that one.
    now += timedelta(days=1)
    [row] = projection_log.grade(now, path, series_for=lambda a: full)
    expected = label_outcomes(_head(full, k + h + 1), h)
    assert row.actual_outcome == CODE_TO_OUTCOME[int(expected.codes[k])]
    assert row.forward_return == pytest.approx(full.close[k + h] / full.close[k] - 1)
    assert row.hit == (row.actual_outcome == p.outcome)
    assert row.graded_through == start + timedelta(days=k + h)

    # Graded once; a later call with more history changes nothing.
    before = projection_log.load(path)
    assert projection_log.grade(now + timedelta(days=60), path, series_for=lambda a: full) == []
    assert projection_log.load(path) == before


def test_summary_sets_hit_rate_beside_the_base_rate(tmp_path):
    e = _event(NOW + timedelta(days=1))
    weak = project(Asset.BTC, e, _result("MARS:RASHI", L.WEAK, base=0.15))
    moderate = project(Asset.ETH, e, _result("MARS:RASHI", L.MODERATE, base=0.2))
    rows = [
        LoggedProjection(projection=weak.model_copy(update={"id": f"w{i}"}), recorded_at=NOW, graded_at=NOW, graded_through=NOW,
                         actual_outcome=Outcome.BIG_UP if hit else Outcome.NEUTRAL, forward_return=0.0, hit=hit)
        for i, hit in enumerate([True, True, False])
    ] + [LoggedProjection(projection=moderate, recorded_at=NOW)]
    track = projection_log.summarize(rows)
    assert (track.total.recorded, track.total.pending, track.total.graded, track.total.hits) == (4, 1, 3, 2)
    assert track.by_label["weak"].hit_rate == pytest.approx(2 / 3)
    assert track.by_label["weak"].avg_base_rate == pytest.approx(0.15)
    assert track.by_label["moderate"].graded == 0 and track.by_label["moderate"].hit_rate is None
    assert list(track.by_label) == ["moderate", "weak"]
    assert len(track.recent) == 3

    path = tmp_path / "log.json"
    path.write_text(json.dumps({"entries": [r.model_dump(mode="json") for r in rows]}), encoding="utf-8")
    assert projection_log.summary(path) == track


# ---------------------------------------------------------------- API


@pytest.fixture
def client():
    warnings.filterwarnings("ignore", message=".*httpx.*")
    from fastapi.testclient import TestClient

    from orbit.api import app as app_module

    return TestClient(app_module.create_app(live=False))


def test_projections_endpoint(client, monkeypatch):
    from orbit.api import store

    upcoming = datetime.now(timezone.utc) + timedelta(days=3)
    pb = _playbook(Asset.BTC, [_result("MARS:RASHI", L.STRONG, h=10), _result("VENUS:RASHI", L.NONE)])
    monkeypatch.setattr(store, "playbook", lambda asset: pb if asset == Asset.BTC else None)
    monkeypatch.setattr(store, "transit_events", lambda: [_event(upcoming), _event(upcoming, planet=Planet.VENUS, to_state="Tula")])
    monkeypatch.setattr(store, "price_series", lambda asset: _walk(300, datetime(2025, 1, 1, tzinfo=timezone.utc)))
    monkeypatch.setattr(store, "regime_by_day", lambda asset: ({datetime(2025, 10, 1, tzinfo=timezone.utc): "BULL"}, "SHARED"))

    rows = client.get("/api/projections").json()
    assert [r["pattern_id"] for r in rows] == ["MARS:RASHI"]
    r = rows[0]
    assert r["asset"] == "BTC" and r["trusted"] is True and r["horizon_days"] == 10
    assert r["horizon_stat"]["horizon_days"] == 10 and r["horizon_stat"]["q_big_up"] == 0.03
    assert r["group_id"] and r["conflict"] is False
    every = client.get("/api/projections", params={"include_none": "true", "days": 10}).json()
    assert {x["pattern_id"] for x in every} == {"MARS:RASHI", "VENUS:RASHI"}


def test_projections_404_before_any_playbook(client, monkeypatch):
    from orbit.api import store

    monkeypatch.setattr(store, "playbook", lambda asset: None)
    r = client.get("/api/projections")
    assert r.status_code == 404 and "playbook" in r.json()["detail"]


def test_projections_track_endpoint(client, monkeypatch, tmp_path):
    monkeypatch.setattr(projection_log, "LOG_PATH", tmp_path / "log.json")
    empty = client.get("/api/projections/track").json()
    assert empty["total"]["recorded"] == 0 and empty["first_recorded_at"] is None and "Nothing graded" in empty["note"]

    p = project(Asset.SILVER, _event(NOW + timedelta(days=1)), _result("MARS:RASHI", L.WEAK))
    projection_log.record([p], NOW)
    body = client.get("/api/projections/track").json()
    assert body["total"]["recorded"] == 1 and body["total"]["pending"] == 1 and body["by_label"]["weak"]["recorded"] == 1


def test_analysis_run_records_and_grades(monkeypatch, tmp_path):
    from orbit.analysis import run, series as series_module

    silver = _walk(400, datetime(2025, 1, 1, tzinfo=timezone.utc))
    (tmp_path / "SILVER.json").write_text(_playbook(Asset.SILVER, [_result("MARS:RASHI", L.WEAK)]).model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(run, "ANALYSIS_DIR", tmp_path)
    monkeypatch.setattr(projection_log, "LOG_PATH", tmp_path / "projections_log.json")
    monkeypatch.setattr(series_module, "load_price_series", lambda asset, until=None, timeframe="1d": silver)
    monkeypatch.setattr(projection_log, "load_price_series", lambda asset, until=None: silver)

    class Rep:
        lines: list[str] = []

        def log(self, line):
            self.lines.append(line)

    rep = Rep()
    upcoming = _event(datetime.now(timezone.utc) + timedelta(days=5))
    out = run._projections(rep, [upcoming], [Asset.SILVER])
    assert out == {"upcoming": 1, "recorded": 1, "graded": 0, "hits": 0}
    assert rep.lines[-1].startswith("Projections: 1 in the next 60 days, 1 newly recorded")
    [row] = projection_log.load()
    assert row.projection.asset == Asset.SILVER and row.graded_at is None
    assert run._projections(rep, [upcoming], [Asset.SILVER])["recorded"] == 0
