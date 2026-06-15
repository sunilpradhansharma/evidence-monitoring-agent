"""Component tests for the read-only JSON API (/api/*) that powers the React dashboard.

These assert the new endpoints surface EXACTLY what render.py already computes (run metrics,
coverage matrix, citation counts, alerts, version-aware questions + counts) and that they are
strictly read-only — they never mutate the store. Writes remain on the existing /approvals/* POST
endpoints (covered elsewhere); this file does not exercise any new write path because none exists.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from evidence_monitor.api import create_app
from evidence_monitor.config.settings import Settings
from evidence_monitor.data_access.interface import RunTotals
from evidence_monitor.data_access.models import (
    Alert,
    AlertRule,
    ApprovalStatus,
    CitationStatus,
    CompetitivePosition,
    Domain,
    Persona,
    Question,
    ScoringRecord,
    TriggerType,
)
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.response_repo.schema import FinishReason, Response, ResponseStatus


def _response(rid: str, *, llm: str, run_id: str, qid: str, status: ResponseStatus) -> Response:
    return Response(
        response_id=rid,
        run_id=run_id,
        question_id=qid,
        target_id=llm,
        llm_name=llm,
        llm_model_version=f"{llm}-v1",
        persona=Persona.PROSPECT,
        therapeutic_area="Area-One",
        brand_focus="Brand-X",
        domain=Domain.EFFICACY,
        response_text=f"Generic answer body for {rid}.",
        response_tokens=10,
        finish_reason=FinishReason.STOP,
        status=status,
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


def _q(qid, persona, text):
    return Question(
        question_id=qid,
        question_text=text,
        persona=persona,
        therapeutic_area="Area-One",
        brand_focus="Brand-X",
        domain=Domain.EFFICACY,
    )


@pytest.fixture
def store():
    s = SqliteStore(":memory:")
    run = s.runs.create(TriggerType.ADHOC)
    rid = run.run_id
    s.responses.insert(
        _response("R1", llm="model-a", run_id=rid, qid="Q-1", status=ResponseStatus.SUCCESS)
    )
    s.responses.insert(
        _response("R2", llm="model-b", run_id=rid, qid="Q-1", status=ResponseStatus.TRUNCATED)
    )
    s.responses.insert(
        _response("R3", llm="model-a", run_id=rid, qid="Q-2", status=ResponseStatus.SUCCESS)
    )
    s.responses.insert(
        _response("R4", llm="model-b", run_id=rid, qid="Q-2", status=ResponseStatus.FAILED)
    )
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
    s.alerts.insert(
        Alert.for_rule(
            score_id=s.scores.latest_for("R3").score_id,
            response_id="R3",
            rule=AlertRule.WRONG_INDICATION,
            reason="Wrong-indication content.",
        )
    )
    s.runs.finalize(
        rid,
        RunTotals(
            questions_attempted=2,
            responses_captured=3,
            failure_count=1,
            total_tokens=1234,
            est_cost=0.0123,
        ),
    )
    # Questions: A-1 edited to v2 then approved (version-aware count = 1); a pending and a rejected.
    s.questions.upsert(_q("A-1", Persona.PROSPECT, "approved one"))
    s.questions.upsert(_q("A-1", Persona.PROSPECT, "approved one v2"))
    s.questions.set_approval("A-1", ApprovalStatus.APPROVED, "rev-a", note="ok")
    s.questions.upsert(_q("P-1", Persona.PROVIDER, "pending one"))
    s.questions.upsert(_q("R-1", Persona.PATIENT, "rejected one"))
    s.questions.set_approval("R-1", ApprovalStatus.REJECTED, "rev-x", reason="off-label")
    s._run_id = rid
    yield s
    s.close()


@pytest.fixture
def client(store):
    app = create_app(store=store, settings=Settings(_env_file=None))
    with TestClient(app) as c:
        c.store = store
        yield c


def _row_counts(store) -> dict[str, int]:
    conn = store.connection
    return {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("responses", "scoring_records", "alerts", "questions", "audit_log", "runs")
    }


# --------------------------------------------------------------------------- #
# /api/runs
# --------------------------------------------------------------------------- #
def test_api_runs_lists_the_run(client):
    runs = client.get("/api/runs").json()
    assert len(runs) == 1
    r = runs[0]
    assert r["run_id"] == client.store._run_id
    assert r["responses_captured"] == 3 and r["failure_count"] == 1
    assert r["started_at"] is not None


# --------------------------------------------------------------------------- #
# /api/runs/{run_id}/report
# --------------------------------------------------------------------------- #
def test_api_report_payload_matches_render(client):
    rid = client.store._run_id
    rep = client.get(f"/api/runs/{rid}/report").json()

    # Metrics — version/run-scoped exactly as render.py computes (4 resp: 2 ok, 1 trunc, 1 fail).
    m = rep["metrics"]
    assert m["total"] == 4 and m["success"] == 2 and m["truncated"] == 1 and m["failed"] == 1
    assert m["failed_blocked"] == 1
    assert round(m["capture_rate"], 5) == 0.75  # (2 success + 1 truncated) / 4
    assert m["capture_ok"] is False  # below the 95% target
    assert m["alert_count"] == 1

    # Coverage matrix: 2 questions × 2 models, with per-cell class/label/truncated/response_id.
    assert rep["coverage"]["models"] == ["model-a", "model-b"]
    rows = {row["question_id"]: row for row in rep["coverage"]["rows"]}
    assert set(rows) == {"Q-1", "Q-2"}
    q1_cells = {c["response_id"]: c for c in rows["Q-1"]["cells"] if c["response_id"]}
    assert q1_cells["R2"]["truncated"] is True  # truncated flag surfaced for click-through cell
    # Q-2 model-a is the wrong-indication response → distinct class.
    q2_classes = {c["klass"] for c in rows["Q-2"]["cells"]}
    assert "wrong_indication" in q2_classes

    # Citation counts include all four statuses; the alert + headline are present.
    assert set(rep["citation_counts"]) == {"CITED", "PARTIAL", "ABSENT", "WRONG_INDICATION"}
    assert rep["citation_counts"]["WRONG_INDICATION"] == 1
    assert rep["alerts"] and rep["alerts"][0]["rules"][0]["rule"] == "WRONG_INDICATION"
    assert rep["alerts"][0]["question_id"] == "Q-2"
    assert isinstance(rep["headline"], str) and rep["headline"]

    # Run meta + sentiment-by-model present.
    assert rep["run"]["total_tokens"] == 1234
    assert {s["name"] for s in rep["sentiment_by_model"]} == {"model-a", "model-b"}


def test_api_report_unknown_run_404(client):
    assert client.get("/api/runs/nope/report").status_code == 404


# --------------------------------------------------------------------------- #
# /api/questions — version-aware list + global counts
# --------------------------------------------------------------------------- #
def test_api_questions_counts_are_version_aware(client):
    payload = client.get("/api/questions", params={"status": "ALL"}).json()
    assert payload["counts"] == {"pending": 1, "approved": 1, "rejected": 1, "total": 3}
    # A-1 has 2 versions but appears exactly once at its current version.
    ids = [q["question_id"] for q in payload["questions"]]
    assert ids.count("A-1") == 1


def test_api_questions_status_and_persona_filter(client):
    pending = client.get("/api/questions", params={"status": "PENDING"}).json()
    assert [q["question_id"] for q in pending["questions"]] == ["P-1"]
    approved = client.get("/api/questions", params={"status": "APPROVED"}).json()
    assert [q["question_id"] for q in approved["questions"]] == ["A-1"]
    assert approved["questions"][0]["approver_name"] == "rev-a"
    none_match = client.get(
        "/api/questions", params={"status": "PENDING", "persona": "PATIENT"}
    ).json()
    assert none_match["questions"] == []  # the only pending question is a PROVIDER one


# --------------------------------------------------------------------------- #
# /api/responses/{id}
# --------------------------------------------------------------------------- #
def test_api_response_returns_text_and_rationale(client):
    body = client.get("/api/responses/R3").json()
    assert body["response_text"] == "Generic answer body for R3."
    assert body["score"]["scoring_rationale"] == "Rationale for R3."
    assert body["score"]["citation_status"] == "WRONG_INDICATION"


def test_api_response_unknown_404(client):
    assert client.get("/api/responses/nope").status_code == 404


# --------------------------------------------------------------------------- #
# Strictly read-only
# --------------------------------------------------------------------------- #
def test_root_and_legacy_html_both_served(client):
    # "/" serves the app (React build if present, else the legacy HTML fallback) — always 200.
    assert client.get("/").status_code == 200
    # The legacy server-rendered UI stays reachable at /html during the transition.
    legacy = client.get("/html")
    assert legacy.status_code == 200
    assert 'data-section="summary"' in legacy.text  # legacy Reports markup still served


def test_api_endpoints_never_write(client):
    before = _row_counts(client.store)
    rid = client.store._run_id
    assert client.get("/api/runs").status_code == 200
    assert client.get(f"/api/runs/{rid}/report").status_code == 200
    assert client.get("/api/questions", params={"status": "ALL"}).status_code == 200
    assert client.get("/api/responses/R1").status_code == 200
    assert client.get("/api/responses").status_code == 200
    assert client.get("/api/alerts").status_code == 200
    assert (
        client.get("/api/comparison", params={"question_id": "Q-1", "run_id": rid}).status_code
        == 200
    )
    assert _row_counts(client.store) == before


# --------------------------------------------------------------------------- #
# /api/responses — Stage 3 table feed (filter / search / paginate)
# --------------------------------------------------------------------------- #
def test_api_responses_table_lists_and_enriches(client):
    body = client.get("/api/responses").json()
    assert body["total"] == 4  # R1..R4
    rows = {r["response_id"]: r for r in body["items"]}
    assert rows["R1"]["sentiment"] == 0.8
    assert rows["R1"]["competitive_position"] == "FIRST_LINE_RECOMMENDED"
    assert rows["R3"]["has_alert"] is True and rows["R1"]["has_alert"] is False
    assert rows["R4"]["status"] == "FAILED" and rows["R4"]["sentiment"] is None


def test_api_responses_table_multiselect_search_and_status(client):
    only_a = client.get("/api/responses", params=[("llm", "model-a")]).json()
    assert {r["response_id"] for r in only_a["items"]} == {"R1", "R3"}
    failed = client.get("/api/responses", params={"status": "FAILED"}).json()
    assert {r["response_id"] for r in failed["items"]} == {"R4"}
    search = client.get("/api/responses", params={"search": "model-b"}).json()
    assert {r["response_id"] for r in search["items"]} == {"R2", "R4"}


def test_api_responses_table_paginates(client):
    p1 = client.get("/api/responses", params={"page": 1, "page_size": 2}).json()
    assert p1["total"] == 4 and len(p1["items"]) == 2 and p1["page"] == 1


# --------------------------------------------------------------------------- #
# /api/alerts — Stage 3 enriched feed + global per-type counts (real engine types only)
# --------------------------------------------------------------------------- #
def test_api_alerts_feed_counts_and_enrichment(client):
    body = client.get("/api/alerts").json()
    assert body["total"] == 1
    # Counts reflect the REAL engine rule types present (no invented types).
    assert body["counts_by_rule"] == {"WRONG_INDICATION": 1}
    assert body["counts_by_type"] == {"wrong-indication": 1}
    item = body["items"][0]
    assert item["model"] == "model-a" and item["rule"] == "WRONG_INDICATION"
    assert item["alert_type"] == "wrong-indication" and item["severity"] == 3
    assert item["sentiment"] == -0.7 and item["question_id"] == "Q-2"


def test_api_alerts_feed_filter_keeps_global_counts(client):
    body = client.get("/api/alerts", params={"rule": "NEGATIVE_SENTIMENT"}).json()
    assert body["items"] == []  # no negative-sentiment alert in the fixture
    assert body["counts_by_rule"] == {"WRONG_INDICATION": 1}  # tiles stay global


# --------------------------------------------------------------------------- #
# /api/comparison — Stage 3 side-by-side
# --------------------------------------------------------------------------- #
def test_api_comparison_columns_per_target(client):
    rid = client.store._run_id
    body = client.get("/api/comparison", params={"question_id": "Q-1", "run_id": rid}).json()
    cols = {c["llm_name"]: c for c in body["columns"]}
    assert set(cols) == {"model-a", "model-b"}
    assert cols["model-a"]["sentiment"] == 0.8
    assert cols["model-a"]["response_text"] == "Generic answer body for R1."


# --------------------------------------------------------------------------- #
# Enriched /api/runs + /api/questions (additive fields for the Stage 3 tables)
# --------------------------------------------------------------------------- #
def test_api_runs_enriched_fields(client):
    run = client.get("/api/runs").json()[0]
    assert run["total_tokens"] == 1234
    assert run["questions_attempted"] == 2
    assert run["alert_count"] == 1
    assert run["status"] == "PARTIAL"  # ended with a failure (failure_count == 1)


def test_api_questions_enriched_fields(client):
    q = client.get("/api/questions", params={"status": "APPROVED"}).json()["questions"][0]
    assert "brand_focus" in q and "active" in q
    assert q["active"] is True
