"""Render tests for the redesigned presentation UI (one per tab).

These assert the presentation + explanatory layer renders from existing records ONLY — the
redesign adds no capture/scoring/alert logic and no write path beyond the existing approve/reject
endpoints. Two focuses:

- **Reports tab**: masthead, "how to read", headline band, the per-run summary cards (including the
  dedicated Truncated and Failed/blocked cards that highlight amber/red), the coverage map, the
  citation-status panel — all scoped to the selected run.
- **Approvals tab**: compliance banner, VERSION-AWARE status counts (latest version per question),
  the reviewer-name gate, the status/persona filters, the writable pending queue, and the
  read-only approved table.
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


@pytest.fixture
def store():
    """One finalized run: a clean cell, a truncated cell, and a failed cell across 2 models +
    2 questions; plus questions in each approval state, one edited to a new version."""
    s = SqliteStore(":memory:")
    run = s.runs.create(TriggerType.ADHOC)
    rid = run.run_id
    # Q-1: model-a favorable, model-b truncated-but-scored.
    s.responses.insert(
        _response("R1", llm="model-a", run_id=rid, qid="Q-1", status=ResponseStatus.SUCCESS)
    )
    s.responses.insert(
        _response("R2", llm="model-b", run_id=rid, qid="Q-1", status=ResponseStatus.TRUNCATED)
    )
    # Q-2: model-a wrong-indication (flagged), model-b failed (no answer).
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
    score_r3 = s.scores.latest_for("R3")
    s.alerts.insert(
        Alert.for_rule(
            score_id=score_r3.score_id,
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

    # Questions across approval states; A-1 is edited (v2) then approved → version-aware count = 1.
    def q(qid, persona, text):
        return Question(
            question_id=qid,
            question_text=text,
            persona=persona,
            therapeutic_area="Area-One",
            brand_focus="Brand-X",
            domain=Domain.EFFICACY,
        )

    s.questions.upsert(q("A-1", Persona.PROSPECT, "approved one"))
    s.questions.upsert(q("A-1", Persona.PROSPECT, "approved one v2"))  # new version
    s.questions.set_approval("A-1", ApprovalStatus.APPROVED, "rev-a", note="ok")
    s.questions.upsert(q("P-1", Persona.PROVIDER, "pending one"))
    s.questions.upsert(q("R-1", Persona.PATIENT, "rejected one"))
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


# --------------------------------------------------------------------------- #
# Reports tab
# --------------------------------------------------------------------------- #
def test_reports_tab_renders_redesigned_presentation(client):
    html = client.get("/html", params={"tab": "reports", "run_id": client.store._run_id}).text

    # Masthead + lede (no "Local Console" / "Local POC" tags).
    assert "Evidence Monitoring AI Agent" in html
    assert "a human approves every question" in html
    assert "Local Console" not in html and "Local POC" not in html

    # Self-explaining panel + headline band.
    assert "How to read this page" in html
    assert 'data-section="headline"' in html

    # Summary cards, incl. the dedicated Truncated (amber) and Failed/blocked (red) cards.
    assert 'data-section="summary"' in html
    assert "Truncated" in html and "Failed / blocked" in html and "Capture rate" in html
    assert "metric warn" in html  # truncated > 0 → amber
    assert "metric bad" in html  # failed > 0 → red

    # Coverage map with legend + the distinct wrong-indication class.
    assert 'data-section="coverage"' in html
    assert "wrong indication" in html
    assert "cell wrong_indication" in html
    assert "model-a" in html and "model-b" in html

    # Citation status panel surfaces the four statuses incl. WRONG_INDICATION.
    assert 'data-section="citation"' in html
    assert "WRONG_INDICATION" in html


def test_reports_summary_is_scoped_to_selected_run(client):
    html = client.get("/html", params={"tab": "reports", "run_id": client.store._run_id}).text
    # The run had 4 responses: 2 SUCCESS, 1 TRUNCATED, 1 FAILED → capture rate 75% (< 95% target).
    assert "4 response(s) in view" in html
    assert "75%" in html
    assert "1234 tokens" in html  # the finalized run's totals on the run line


# --------------------------------------------------------------------------- #
# Approvals tab
# --------------------------------------------------------------------------- #
def test_approvals_tab_renders_redesigned_presentation(client):
    html = client.get("/html", params={"tab": "approvals"}).text

    # Compliance banner.
    assert 'data-section="compliance"' in html
    assert "audit log" in html

    # Version-aware status counts (A-1 edited to v2 then approved → counted once).
    assert 'data-section="approval-counts"' in html
    assert (
        "Pending" in html
        and "Approved" in html
        and "Rejected" in html
        and "Total questions" in html
    )

    # Reviewer-name gate: field present, action buttons disabled until a name is entered.
    assert 'id="approver"' in html
    assert "Reviewer name" in html
    assert "act-btn" in html and "disabled" in html

    # Status + persona filters.
    assert 'data-section="approval-filters"' in html
    assert 'name="status"' in html and 'name="persona"' in html

    # Writable pending queue + read-only approved table.
    assert "Pending questions" in html
    assert "data-question-id=" in html
    assert "Approved questions (1)" in html  # version-aware: A-1 counted once despite v2


def test_lists_show_each_question_once_despite_version_history(client):
    """Dedup bug guard: a question with multiple versions must render exactly ONCE in its list,
    at its current version — pending, approved, and rejected lists alike (version-aware rows)."""
    from evidence_monitor.question_repo.repository import QuestionService

    store = client.store
    svc = QuestionService(store.questions)

    def q(qid, text, persona=Persona.PROVIDER):
        return Question(
            question_id=qid,
            question_text=text,
            persona=persona,
            therapeutic_area="Area-One",
            brand_focus="Brand-X",
            domain=Domain.EFFICACY,
        )

    # Pending question edited to v2/v3 (stays PENDING) → one card in the pending queue.
    store.questions.upsert(q("P-DUP", "v1"))
    store.questions.upsert(q("P-DUP", "v2"))
    store.questions.upsert(q("P-DUP", "v3"))
    # Approved question edited AFTER approval (edit retains APPROVED) → one row in approved table.
    store.questions.upsert(q("A-DUP", "a1", persona=Persona.PATIENT))
    store.questions.set_approval("A-DUP", ApprovalStatus.APPROVED, "rev")
    svc.edit("A-DUP", question_text="a2")  # v3, still APPROVED
    # Rejected question with extra versions → one row in rejected table.
    store.questions.upsert(q("R-DUP", "r1", persona=Persona.PROSPECT))
    store.questions.upsert(q("R-DUP", "r2", persona=Persona.PROSPECT))
    store.questions.set_approval("R-DUP", ApprovalStatus.REJECTED, "rev", reason="off-label")

    html = client.get("/html", params={"tab": "approvals", "status": "ALL"}).text
    assert html.count('data-question-id="P-DUP"') == 1  # pending: once despite 3 versions
    assert html.count("<td>A-DUP</td>") == 1  # approved table: once despite 3 versions
    assert html.count("<td>R-DUP</td>") == 1  # rejected table: once despite 3 versions


def test_approval_gate_counts_are_version_aware(client):
    # Approve a second question AFTER editing it; the gate must count latest versions only.
    store = client.store
    store.questions.upsert(
        Question(
            question_id="A-1",
            question_text="approved one v3",
            persona=Persona.PROSPECT,
            therapeutic_area="Area-One",
            brand_focus="Brand-X",
            domain=Domain.EFFICACY,
        )
    )  # bump A-1 to v3 (still APPROVED-eligible after re-approval)
    store.questions.set_approval("A-1", ApprovalStatus.APPROVED, "rev-a2")
    html = client.get("/html", params={"tab": "approvals"}).text
    # A-1 has 3 versions but counts exactly once as Approved; P-1 pending, R-1 rejected.
    assert "<b>1</b> Approved" in html
    assert "<b>1</b> Pending" in html
    assert "<b>1</b> Rejected" in html
    assert "<b>3</b> Total questions" in html
