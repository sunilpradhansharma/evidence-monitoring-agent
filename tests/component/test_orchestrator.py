"""Component tests for the orchestration graph (US1; Principles VIII & IX).

Runs the explicit LangGraph flow end-to-end in deterministic OFFLINE/MOCK mode (no network, no
keys). Covers the two behaviors the task calls out:

1. **Full fan-out over the seed** — every APPROVED question reaches every eligible target, each
   response is persisted, scored, and summarized; the conditional Open Evidence target is excluded.
2. **Resume after interruption** — a run that already completed the first question resumes from the
   next one without re-submitting the completed question (no duplicate responses).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.fixtures import sample_questions

from evidence_monitor.data_access.interface import QueryFilters
from evidence_monitor.data_access.models import (
    AlertRule,
    ApprovalStatus,
    AuditEventType,
    CitationStatus,
    CompetitivePosition,
    ScoringRecord,
    TriggerType,
)
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.llm.client import ClaudeClient
from evidence_monitor.llm.registry import build_adapter, load_targets, targets_for_persona
from evidence_monitor.orchestrator import OrchestratorContext, RunManager, run
from evidence_monitor.response_repo.repository import ResponseService
from evidence_monitor.response_repo.schema import Response
from evidence_monitor.scoring.scorer import Scored, Scorer

# repo-root/src/evidence_monitor/config/targets.yaml (tests/component/<file> → parents[2] == root)
TARGETS_CFG = Path(__file__).resolve().parents[2] / "src/evidence_monitor/config/targets.yaml"


@pytest.fixture
def store():
    s = SqliteStore(":memory:")
    yield s
    s.close()


@pytest.fixture
def targets():
    return load_targets(TARGETS_CFG)


def _seed_approved_questions(store: SqliteStore) -> None:
    """Insert the seed questions and approve all three (so the run has a full fan-out)."""
    for q in sample_questions():
        store.questions.upsert(q)
        store.questions.set_approval(q.question_id, ApprovalStatus.APPROVED, "reviewer")


def _make_context(store, targets, **kwargs) -> OrchestratorContext:
    return OrchestratorContext(
        store=store,
        targets=targets,
        scorer=Scorer(ClaudeClient(model_id="scorer-model-1", mock=True)),
        run_manager=RunManager(store.runs),
        **kwargs,
    )


def _expected_pairs(store, targets) -> set[tuple[str, str]]:
    """Every (question_id, target_id) pair that SHOULD be produced (the fan-out)."""
    return {
        (q.question_id, t.target_id)
        for q in store.questions.approved_active()
        for t in targets_for_persona(targets, q.persona)
    }


def _responses_by_question(store) -> dict[str, int]:
    rows = ResponseService(store.responses).query(QueryFilters(), page_size=None).items
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.question_id] = counts.get(r.question_id, 0) + 1
    return counts


# --------------------------------------------------------------------------- #
# 1. Full fan-out over the seed
# --------------------------------------------------------------------------- #
def test_full_fanout_over_seed(store, targets):
    _seed_approved_questions(store)
    expected_pairs = _expected_pairs(store, targets)
    # 10 = PROSPECT + PATIENT questions × 3 unconditional targets, plus the PROVIDER question × 4:
    # the 3 unconditional targets and the active PROVIDER-only provider-evidence-dev target.
    assert len(expected_pairs) == 10

    final = run(_make_context(store, targets), trigger=TriggerType.ADHOC)

    # Every (question × eligible target) produced exactly one response.
    assert {(r.question_id, r.target_id) for r in final.responses} == expected_pairs
    assert len(final.responses) == 10
    # The inactive, conditional Open Evidence target never fires (FR-007).
    assert "open-evidence" not in {r.target_id for r in final.responses}
    # The active PROVIDER-only dev stand-in does fire (operator-enabled in config).
    assert "provider-evidence-dev" in {r.target_id for r in final.responses}

    # Every captured response was scored into a separate versioned record (US2).
    assert len(final.scores) == 10
    for response in final.responses:
        assert store.scores.latest_for(response.response_id) is not None

    # Mock responses are neutral, so no alert fires (deterministic; Principle VIII).
    assert final.alerts == []

    # Summary + run finalization (FR-026).
    assert final.summary.questions_attempted == 3
    assert final.summary.responses_captured == 10
    assert final.summary.responses_by_status == {"SUCCESS": 10}
    assert final.summary.alert_count == 0
    assert final.summary.total_tokens > 0
    assert store.runs.get(final.run_id).ended_at is not None


def test_full_fanout_writes_audit_trail(store, targets):
    _seed_approved_questions(store)
    run(_make_context(store, targets))

    counts: dict[str, int] = {}
    query = "SELECT event_type, COUNT(*) FROM audit_log GROUP BY event_type"
    for row in store.connection.execute(query):
        counts[row[0]] = row[1]

    assert counts[str(AuditEventType.RUN_STARTED)] == 1
    assert counts[str(AuditEventType.RUN_ENDED)] == 1
    # 10 dispatched/received = full persona-aware fan-out (PROVIDER question also reaches the active
    # provider-evidence-dev target).
    assert counts[str(AuditEventType.QUERY_DISPATCHED)] == 10
    assert counts[str(AuditEventType.RESPONSE_RECEIVED)] == 10


def test_run_only_dispatches_approved_questions(store, targets):
    # One APPROVED, two PENDING — only the approved one is ever submitted (FR-003).
    for q in sample_questions():
        store.questions.upsert(q)
    store.questions.set_approval("Q-PROS-1", ApprovalStatus.APPROVED, "reviewer")

    final = run(_make_context(store, targets))

    assert {r.question_id for r in final.responses} == {"Q-PROS-1"}


# --------------------------------------------------------------------------- #
# 2. Resume after interruption — skip completed questions, no duplicates
# --------------------------------------------------------------------------- #
def _simulate_first_question_completed(store, targets, run_id: str) -> str:
    """Persist the first question's responses + checkpoint, mimicking an interrupted run."""
    responses = ResponseService(store.responses)
    question = store.questions.approved_active()[0]
    for target in targets_for_persona(targets, question.persona):
        result = build_adapter(target, mock=True).submit(
            question_text=question.question_text,
            persona=question.persona,
            system_prompt="You are a helpful assistant.",
        )
        responses.record(
            Response(
                run_id=run_id,
                question_id=question.question_id,
                target_id=target.target_id,
                llm_name=target.llm_name,
                llm_model_version=result.model_version,
                persona=question.persona,
                therapeutic_area=question.therapeutic_area,
                brand_focus=question.brand_focus,
                domain=question.domain,
                response_text=result.response_text,
                response_tokens=result.response_tokens,
                finish_reason=result.finish_reason,
                status=result.status,
                block_reason=result.block_reason,
            )
        )
    RunManager(store.runs).checkpoint(run_id, question.question_id)
    return question.question_id


def test_resume_skips_completed_questions_without_duplicates(store, targets):
    _seed_approved_questions(store)
    approved = store.questions.approved_active()
    assert len(approved) == 3

    # Start a run and simulate an interruption after the first question completed.
    interrupted = RunManager(store.runs).start(TriggerType.SCHEDULED)
    done_qid = _simulate_first_question_completed(store, targets, interrupted.run_id)
    remaining_qids = {q.question_id for q in approved if q.question_id != done_qid}

    # Persona-aware fan-out: the PROVIDER question reaches 4 active targets (incl. provider-evidence-
    # dev) and the others 3, so per-question counts are NOT uniform. Total over the bank is 10.
    fanout = {q.question_id: len(targets_for_persona(targets, q.persona)) for q in approved}
    total_fanout = sum(fanout.values())

    # Resume the SAME run.
    final = run(_make_context(store, targets, resume_run_id=interrupted.run_id))

    # Same run id — no new run was created on resume.
    assert final.run_id == interrupted.run_id
    # The resumed invocation dispatched ONLY the not-yet-completed questions.
    assert {r.question_id for r in final.responses} == remaining_qids
    assert len(final.responses) == sum(fanout[qid] for qid in remaining_qids)
    assert final.cursor == 3  # cursor advanced past the last question

    # The completed question was NOT re-submitted: it still has exactly its persona's fan-out, and
    # the store holds the full fan-out once (no duplicates).
    per_question = _responses_by_question(store)
    assert per_question[done_qid] == fanout[done_qid]
    assert per_question == fanout
    assert sum(per_question.values()) == total_fanout

    # Resume scores the WHOLE run, including the responses captured before the interruption.
    assert len(final.scores) == total_fanout
    run_responses = (
        ResponseService(store.responses)
        .query(QueryFilters(run_id=interrupted.run_id), page_size=None)
        .items
    )
    assert all(store.scores.latest_for(r.response_id) is not None for r in run_responses)


class _CompetitorScorer:
    """Stub scorer that reports a competitor far more positive than our therapy (gap-2 wiring)."""

    def score(self, response: Response) -> Scored:
        record = ScoringRecord(
            response_id=response.response_id,
            sentiment_score=0.0,
            competitive_position=CompetitivePosition.AMONG_OPTIONS,
            citation_status=CitationStatus.CITED,
            brand_mentions=["rival"],
            competitor_sentiments={"rival": 0.9},  # 0.9 vs our 0.0 → exceeds the 0.3 margin
            key_claims=[],
            scoring_rationale="stub",
            scorer_model="stub-model",
        )
        return Scored(record=record, tokens=1)


def test_competitor_higher_alert_fires_through_the_pipeline(store, targets):
    # Closes the COMPETITOR_HIGHER gap: per-competitor sentiment now flows score → rule → alert.
    _seed_approved_questions(store)
    ctx = OrchestratorContext(
        store=store,
        targets=targets,
        scorer=_CompetitorScorer(),
        run_manager=RunManager(store.runs),
    )

    final = run(ctx)

    assert final.alerts, "expected COMPETITOR_HIGHER alerts to fire"
    assert {a.rule_fired for a in final.alerts} == {AlertRule.COMPETITOR_HIGHER}
    assert final.summary.alert_count == len(final.alerts)
