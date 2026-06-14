"""Component tests for the Reports view (US5): four sections render from seed data, the static
export is self-contained (FR-603), and every Reports endpoint is strictly read-only.

Drives both the shared render path (``dashboard.render``) and the served ``/reports/*`` JSON
endpoints over an injected in-memory store. The same render logic backs the served Reports tab and
the shareable static HTML, so they are asserted together.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from evidence_monitor.api import create_app
from evidence_monitor.dashboard.render import (
    build_report,
    render_reports_section,
    render_static_report,
)
from evidence_monitor.data_access.models import (
    Alert,
    AlertRule,
    CitationStatus,
    CompetitivePosition,
    Domain,
    Persona,
    ScoringRecord,
    TriggerType,
)
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.response_repo.schema import FinishReason, Response, ResponseStatus

_SECTIONS = (
    'data-section="sentiment"',
    'data-section="positioning"',
    'data-section="alerts"',
    'data-section="volume"',
)


def _response(rid: str, *, llm: str, ta: str, persona: Persona, run_id: str) -> Response:
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
        status=ResponseStatus.SUCCESS,
    )


def _score(
    rid: str,
    *,
    sentiment: float,
    position: CompetitivePosition,
    citation: CitationStatus = CitationStatus.CITED,
) -> ScoringRecord:
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
def store():
    s = SqliteStore(":memory:")
    run = s.runs.create(TriggerType.ADHOC)
    # Two LLMs, two therapeutic areas, a spread of sentiment + positions.
    s.responses.insert(
        _response("R1", llm="llm-a", ta="Area-One", persona=Persona.PROSPECT, run_id=run.run_id)
    )
    s.responses.insert(
        _response("R2", llm="llm-b", ta="Area-Two", persona=Persona.PROVIDER, run_id=run.run_id)
    )
    s.responses.insert(
        _response("R3", llm="llm-a", ta="Area-Two", persona=Persona.PATIENT, run_id=run.run_id)
    )
    s.scores.add_version(
        _score("R1", sentiment=0.7, position=CompetitivePosition.FIRST_LINE_RECOMMENDED)
    )
    s.scores.add_version(
        _score(
            "R2",
            sentiment=-0.6,
            position=CompetitivePosition.NOT_RECOMMENDED,
            citation=CitationStatus.WRONG_INDICATION,
        )
    )
    s.scores.add_version(_score("R3", sentiment=0.0, position=CompetitivePosition.AMONG_OPTIONS))
    score_r2 = s.scores.latest_for("R2")
    s.alerts.insert(
        Alert.for_rule(
            score_id=score_r2.score_id,
            response_id="R2",
            rule=AlertRule.WRONG_INDICATION,
            reason="Wrong-indication content.",
        )
    )
    s._run_id = run.run_id  # expose for the summary test
    yield s
    s.close()


@pytest.fixture
def client(store):
    app = create_app(store=store)
    with TestClient(app) as c:
        c.store = store
        yield c


# --------------------------------------------------------------------------- #
# Four sections render from seed data
# --------------------------------------------------------------------------- #
def test_reports_section_renders_all_four_sections(store):
    html = render_reports_section(build_report(store), interactive=False)
    for marker in _SECTIONS:
        assert marker in html
    # Seed dimensions surface in the aggregates.
    assert "llm-a" in html and "llm-b" in html
    assert "Area-One" in html and "Area-Two" in html
    assert "NOT_RECOMMENDED" in html  # competitive-positioning column
    assert "WRONG_INDICATION" in html  # flagged alert rule


def test_static_export_is_self_contained(store):
    doc = render_static_report(build_report(store), generated_at="2026-06-13")
    assert doc.strip().startswith("<!doctype html>")
    assert "<style>" in doc  # inline CSS — no external assets
    for marker in _SECTIONS:
        assert marker in doc
    # Drill-down evidence travels with the file (FR-024 / FR-603): full text + rationale present.
    assert "Generic answer body for R2." in doc
    assert "Rationale for R2." in doc


def test_served_reports_tab_uses_same_render(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    assert "Reports" in body and "Approvals" in body  # tabs
    for marker in _SECTIONS:
        assert marker in body


# --------------------------------------------------------------------------- #
# Reports endpoints are strictly read-only
# --------------------------------------------------------------------------- #
def _row_counts(store) -> dict[str, int]:
    conn = store.connection
    return {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("responses", "scoring_records", "alerts", "questions", "audit_log", "runs")
    }


def test_reports_endpoints_never_write(client):
    before = _row_counts(client.store)
    run_id = client.store._run_id

    assert client.get("/").status_code == 200
    assert client.get("/reports/responses").status_code == 200
    assert client.get("/reports/responses/R2").status_code == 200
    assert client.get("/reports/alerts").status_code == 200
    assert client.get("/reports/export", params={"format": "csv"}).status_code == 200
    assert client.get("/reports/export", params={"format": "json"}).status_code == 200
    assert client.get(f"/reports/runs/{run_id}/summary").status_code == 200

    assert _row_counts(client.store) == before  # nothing mutated by any read path


def test_reports_responses_filter_and_drilldown(client):
    # Filter by LLM narrows the set; drill-down returns full text + scoring versions + alerts.
    only_a = client.get("/reports/responses", params={"llm": "llm-a"}).json()
    assert only_a["total"] == 2
    assert all(item["llm_name"] == "llm-a" for item in only_a["items"])

    drill = client.get("/reports/responses/R2").json()
    assert drill["response"]["response_text"] == "Generic answer body for R2."
    assert len(drill["scoring_versions"]) == 1
    assert drill["alerts"][0]["rule_fired"] == "WRONG_INDICATION"


def test_alerts_ordered_by_severity(client):
    alerts = client.get("/reports/alerts").json()
    assert alerts and alerts[0]["rule_fired"] == "WRONG_INDICATION"  # highest severity first


def test_run_summary_reports_by_status(client):
    summary = client.get(f"/reports/runs/{client.store._run_id}/summary").json()
    assert summary["responses_by_status"] == {"SUCCESS": 3}
    assert summary["alert_count"] == 1


def test_export_csv_matches_filtered_view(client):
    csv_all = client.get("/reports/export", params={"format": "csv"}).text
    # Header + 3 data rows.
    assert csv_all.count("\n") >= 3
    csv_a = client.get("/reports/export", params={"format": "csv", "llm": "llm-a"}).text
    assert "llm-b" not in csv_a and "llm-a" in csv_a
