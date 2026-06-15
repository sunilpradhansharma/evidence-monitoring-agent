"""Component tests for the read-only Dashboard aggregate (render.build_dashboard) and the
/api/dashboard endpoint that surfaces it.

Focus areas:
- the dashboard re-shapes ONLY already-stored records (KPIs, histogram, positioning, heatmap,
  volume-by-week, recent alerts) — it adds no capture/scoring/alert logic;
- the PROVIDER-only dev stand-in (provider-evidence-dev) is classified as a limited/dev target
  (``is_full_llm=False``) and is EXCLUDED from KPIs/charts by default, but still listed so the UI
  can offer the "Include Provider evidence (dev)" toggle;
- the filter bar (persona / LLM multi-select / therapy / period) and the include_dev toggle drive
  every widget;
- the endpoint is strictly read-only.

Real config target names are used so the endpoint's config-driven classification (a target that
serves every persona is a full LLM; provider-only is limited) is exercised end-to-end.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evidence_monitor.api import create_app
from evidence_monitor.config.settings import Settings
from evidence_monitor.dashboard.render import build_dashboard
from evidence_monitor.data_access.interface import QueryFilters, RunTotals
from evidence_monitor.data_access.models import (
    Alert,
    AlertRule,
    CitationStatus,
    CompetitivePosition,
    Domain,
    Persona,
    Question,
    ScoringRecord,
    TriggerType,
)
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.llm.registry import load_targets
from evidence_monitor.response_repo.schema import FinishReason, Response, ResponseStatus

TARGETS_CFG = Path(__file__).resolve().parents[2] / "src/evidence_monitor/config/targets.yaml"

# Structural provider ids from config (NOT regulated content). The first two serve every persona
# (full LLMs); provider-evidence-dev is PROVIDER-only (the limited/dev stand-in).
_LLM_A = "openai-gpt4o"
_LLM_B = "google-gemini"
_DEV = "provider-evidence-dev"


def _resp(
    rid: str,
    *,
    llm: str,
    persona: Persona,
    ta: str,
    status: ResponseStatus,
    ts: datetime,
    run_id: str,
) -> Response:
    return Response(
        response_id=rid,
        run_id=run_id,
        question_id=f"Q-{rid}",
        target_id=llm,
        llm_name=llm,
        llm_model_version=f"{llm}-v1",
        persona=persona,
        therapeutic_area=ta,
        brand_focus="Brand-X",
        domain=Domain.EFFICACY,
        response_text=f"Generic answer body for {rid}.",
        response_tokens=10,
        finish_reason=FinishReason.STOP,
        status=status,
        timestamp_utc=ts,
    )


def _score(rid: str, *, sentiment: float, position: CompetitivePosition, citation: CitationStatus):
    return ScoringRecord(
        response_id=rid,
        sentiment_score=sentiment,
        competitive_position=position,
        citation_status=citation,
        brand_mentions=["Brand-X"],
        key_claims=["Generic claim."],
        scoring_rationale=f"Rationale for {rid}.",
        scorer_model="scorer-1",
    )


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
def store(now):
    """A small cross-target, cross-persona, cross-week dataset.

    R1 is 10 days old (outside a 7d window, inside 30d); the rest are current. R5 is the dev target.
    """
    s = SqliteStore(":memory:")
    run = s.runs.create(TriggerType.ADHOC)
    rid = run.run_id
    old = now - timedelta(days=10)

    rows = [
        # full LLMs
        _resp(
            "R1",
            llm=_LLM_A,
            persona=Persona.PROSPECT,
            ta="Area-One",
            status=ResponseStatus.SUCCESS,
            ts=old,
            run_id=rid,
        ),
        _resp(
            "R2",
            llm=_LLM_B,
            persona=Persona.PROSPECT,
            ta="Area-One",
            status=ResponseStatus.TRUNCATED,
            ts=now,
            run_id=rid,
        ),
        _resp(
            "R3",
            llm=_LLM_A,
            persona=Persona.PROVIDER,
            ta="Area-Two",
            status=ResponseStatus.SUCCESS,
            ts=now,
            run_id=rid,
        ),
        _resp(
            "R4",
            llm=_LLM_B,
            persona=Persona.PROVIDER,
            ta="Area-Two",
            status=ResponseStatus.FAILED,
            ts=now,
            run_id=rid,
        ),
        # PROVIDER-only dev stand-in
        _resp(
            "R5",
            llm=_DEV,
            persona=Persona.PROVIDER,
            ta="Area-Two",
            status=ResponseStatus.SUCCESS,
            ts=now,
            run_id=rid,
        ),
    ]
    for r in rows:
        s.responses.insert(r)

    s.scores.add_version(
        _score(
            "R1",
            sentiment=0.8,
            position=CompetitivePosition.FIRST_LINE_RECOMMENDED,
            citation=CitationStatus.CITED,
        )
    )
    s.scores.add_version(
        _score(
            "R2",
            sentiment=0.1,
            position=CompetitivePosition.AMONG_OPTIONS,
            citation=CitationStatus.PARTIAL,
        )
    )
    s.scores.add_version(
        _score(
            "R3",
            sentiment=-0.7,
            position=CompetitivePosition.NOT_RECOMMENDED,
            citation=CitationStatus.WRONG_INDICATION,
        )
    )
    # R4 FAILED → no score. R5 (dev) is scored so the toggle has something to add.
    s.scores.add_version(
        _score(
            "R5",
            sentiment=0.5,
            position=CompetitivePosition.AMONG_OPTIONS,
            citation=CitationStatus.CITED,
        )
    )
    s.alerts.insert(
        Alert.for_rule(
            score_id=s.scores.latest_for("R3").score_id,
            response_id="R3",
            rule=AlertRule.WRONG_INDICATION,
            reason="Wrong-indication content.",
        )
    )
    # The flagged response's question, so recent-alerts can resolve its text.
    s.questions.upsert(
        Question(
            question_id="Q-R3",
            question_text="Provider dosing question.",
            persona=Persona.PROVIDER,
            therapeutic_area="Area-Two",
            brand_focus="Brand-X",
            domain=Domain.SAFETY,
        )
    )
    s.runs.finalize(
        rid,
        RunTotals(
            questions_attempted=5,
            responses_captured=4,
            failure_count=1,
            total_tokens=999,
            est_cost=0.05,
        ),
    )
    s._run_id = rid
    yield s
    s.close()


@pytest.fixture
def targets():
    return load_targets(TARGETS_CFG)


@pytest.fixture
def client(store):
    app = create_app(store=store, settings=Settings(_env_file=None))
    with TestClient(app) as c:
        c.store = store
        yield c


def _by_id(items):
    return {i["target_id"]: i for i in items}


# --------------------------------------------------------------------------- #
# Target classification + the include_dev default (dev EXCLUDED by default)
# --------------------------------------------------------------------------- #
def test_dev_target_classified_and_excluded_by_default(store, targets):
    data = build_dashboard(store, targets=targets)  # include_dev defaults to False

    metas = {t.target_id: t for t in data.targets}
    # All three present in the classification list (so the UI can render the toggle)...
    assert set(metas) == {_LLM_A, _LLM_B, _DEV}
    assert metas[_LLM_A].is_full_llm is True and metas[_LLM_A].kind == "llm"
    assert metas[_DEV].is_full_llm is False and metas[_DEV].kind == "dev"

    # ...but the dev target contributes to NONE of the aggregate widgets by default.
    assert _DEV not in {s.target_id for s in data.histogram}
    assert _DEV not in {s.target_id for s in data.positioning}
    assert _DEV not in {row.target_id for row in data.heatmap}


def test_kpis_over_full_llms_only_by_default(store, targets):
    k = build_dashboard(store, targets=targets).kpis
    # Only the 4 full-LLM responses (R1..R4) count; the dev R5 is excluded.
    assert k.responses_total == 4
    assert k.responses_captured == 3  # R1 SUCCESS, R2 TRUNCATED, R3 SUCCESS (R4 FAILED)
    assert k.success_rate == pytest.approx(0.75)
    assert k.scored == 3  # R1, R2, R3 (R4 unscored, R5 dev excluded)
    assert k.avg_sentiment == pytest.approx((0.8 + 0.1 - 0.7) / 3)
    assert k.favourable == 2 and k.favourable_pct == pytest.approx(2 / 3)  # FIRST_LINE + AMONG
    assert k.active_alerts == 1
    assert k.last_run is not None and k.last_run.total_tokens == 999


def test_include_dev_folds_in_the_dev_target(store, targets):
    data = build_dashboard(store, targets=targets, include_dev=True)
    assert _DEV in {s.target_id for s in data.histogram}
    # Order: full LLMs first (alphabetical), the limited/dev target last.
    assert [s.target_id for s in data.histogram][-1] == _DEV

    k = data.kpis
    assert k.responses_total == 5 and k.scored == 4  # adds the dev R5
    assert k.avg_sentiment == pytest.approx((0.8 + 0.1 - 0.7 + 0.5) / 4)
    assert k.favourable == 3  # R1 FIRST_LINE, R2 AMONG, R5 AMONG


# --------------------------------------------------------------------------- #
# Widgets: histogram buckets, positioning, heatmap n/a, volume-by-week, recent alerts
# --------------------------------------------------------------------------- #
def test_histogram_buckets_span_full_scale(store, targets):
    data = build_dashboard(store, targets=targets)
    assert data.bucket_edges[0] == -1.0 and data.bucket_edges[-1] == 1.0
    series = {s.target_id: s.counts for s in data.histogram}
    assert all(len(c) == len(data.bucket_edges) - 1 for c in series.values())
    # llm-A: 0.8 → top bucket, -0.7 → a low bucket. Two scored responses total for A.
    assert sum(series[_LLM_A]) == 2
    assert series[_LLM_A][-1] == 1  # the +0.8 lands in the last (+0.75..+1.0) bucket


def test_positioning_counts_per_target(store, targets):
    data = build_dashboard(store, targets=targets)
    series = {s.target_id: s for s in data.positioning}
    a = series[_LLM_A]
    assert a.total == 2
    assert a.counts.get("FIRST_LINE_RECOMMENDED") == 1
    assert a.counts.get("NOT_RECOMMENDED") == 1


def test_heatmap_has_na_cell_where_no_data(store, targets):
    data = build_dashboard(store, targets=targets)
    assert data.therapeutic_areas == ["Area-One", "Area-Two"]
    rows = {row.target_id: {c.therapeutic_area: c for c in row.cells} for row in data.heatmap}
    # llm-B answered Area-One (R2, scored) but its Area-Two response (R4) FAILED → no score → n/a.
    assert rows[_LLM_B]["Area-One"].mean == pytest.approx(0.1)
    assert rows[_LLM_B]["Area-Two"].mean is None and rows[_LLM_B]["Area-Two"].count == 0
    # llm-A has both areas scored.
    assert rows[_LLM_A]["Area-One"].mean == pytest.approx(0.8)
    assert rows[_LLM_A]["Area-Two"].mean == pytest.approx(-0.7)


def test_volume_by_week_splits_by_status_across_weeks(store, targets):
    data = build_dashboard(store, targets=targets)
    # R1 is 10 days older than the rest → two distinct ISO weeks.
    assert len(data.volume_by_week) == 2
    for wk in data.volume_by_week:
        assert set(wk.counts) == {"SUCCESS", "TRUNCATED", "BLOCKED", "FAILED"}
    totals = {st: sum(wk.counts[st] for wk in data.volume_by_week) for st in ("SUCCESS", "FAILED")}
    assert totals["SUCCESS"] == 2 and totals["FAILED"] == 1  # full-LLM only (dev excluded)


def test_recent_alerts_surface_flagged_response(store, targets):
    data = build_dashboard(store, targets=targets)
    assert len(data.recent_alerts) == 1
    a = data.recent_alerts[0]
    assert a.response_id == "R3" and a.model == _LLM_A
    assert a.alert_type == "wrong-indication"
    assert a.sentiment == pytest.approx(-0.7)
    assert a.question_text == "Provider dosing question."  # resolved via the question lookup


# --------------------------------------------------------------------------- #
# View-layer filters (in-memory) — persona, LLM multi-select, period
# --------------------------------------------------------------------------- #
def test_llm_multiselect_filters_series(store, targets):
    data = build_dashboard(store, targets=targets, llms={_LLM_A}, include_dev=True)
    assert {s.target_id for s in data.histogram} == {_LLM_A}


def test_period_filter_excludes_older_responses(store, targets, now):
    # A 7-day window drops R1 (10 days old): llm-A then has only its current PROVIDER response (R3).
    filters = QueryFilters(date_from=now - timedelta(days=7))
    data = build_dashboard(store, filters=filters, targets=targets)
    a = {s.target_id: s for s in data.positioning}[_LLM_A]
    assert a.total == 1 and a.counts.get("NOT_RECOMMENDED") == 1


# --------------------------------------------------------------------------- #
# /api/dashboard endpoint — plumbing + read-only
# --------------------------------------------------------------------------- #
def test_endpoint_default_excludes_dev(client):
    body = client.get("/api/dashboard").json()
    assert body["include_dev"] is False
    metas = _by_id(body["targets"])
    assert metas[_DEV]["is_full_llm"] is False and metas[_DEV]["kind"] == "dev"
    assert _DEV not in {s["target_id"] for s in body["sentiment_histogram"]["series"]}
    assert body["kpis"]["responses_total"] == 4


def test_endpoint_include_dev_true(client):
    body = client.get("/api/dashboard", params={"include_dev": "true"}).json()
    assert body["include_dev"] is True
    assert _DEV in {s["target_id"] for s in body["sentiment_histogram"]["series"]}
    assert body["kpis"]["responses_total"] == 5


def test_endpoint_persona_filter(client):
    body = client.get("/api/dashboard", params={"persona": "PROSPECT"}).json()
    # Only PROSPECT responses (R1, R2) are full-LLM and in scope.
    assert body["kpis"]["responses_total"] == 2


def test_endpoint_llm_multiselect(client):
    body = client.get("/api/dashboard", params=[("llm", _LLM_A), ("include_dev", "true")]).json()
    assert {s["target_id"] for s in body["sentiment_histogram"]["series"]} == {_LLM_A}


def test_endpoint_period_7d(client):
    body = client.get("/api/dashboard", params={"period": "7d"}).json()
    # R1 (10 days old) drops out → 3 full-LLM responses remain (R2, R3, R4).
    assert body["kpis"]["responses_total"] == 3


def test_endpoint_is_read_only(client):
    def counts():
        conn = client.store.connection
        return {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("responses", "scoring_records", "alerts", "questions", "audit_log", "runs")
        }

    before = counts()
    assert client.get("/api/dashboard").status_code == 200
    assert (
        client.get("/api/dashboard", params={"include_dev": "true", "period": "30d"}).status_code
        == 200
    )
    assert counts() == before
