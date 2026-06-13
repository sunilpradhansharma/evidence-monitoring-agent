"""Round-trip tests for the SQLite store: immutability, versioning, soft-delete, run lifecycle."""

from __future__ import annotations

import pytest
from tests.fixtures import (
    sample_alert,
    sample_questions,
    sample_response,
    sample_scoring,
)

from evidence_monitor.data_access.interface import (
    DataAccess,
    RunTotals,
)
from evidence_monitor.data_access.models import ApprovalStatus, TriggerType
from evidence_monitor.data_access.sqlite_store import SqliteStore


@pytest.fixture
def store():
    s = SqliteStore(":memory:")
    yield s
    s.close()


def test_store_satisfies_data_access_protocol(store):
    assert isinstance(store, DataAccess)


def test_question_upsert_versions_and_approved_active(store):
    q = sample_questions()[1]  # PENDING provider question
    store.questions.upsert(q)
    assert store.questions.approved_active() == []  # PENDING is not eligible

    approved = store.questions.set_approval(q.question_id, ApprovalStatus.APPROVED, "reviewer")
    assert approved.version == 2  # transition recorded as a new version (history kept)
    assert approved.approval_status is ApprovalStatus.APPROVED
    eligible = store.questions.approved_active()
    assert [e.question_id for e in eligible] == [q.question_id]


def test_question_soft_delete_keeps_history(store):
    q = sample_questions()[0]
    store.questions.upsert(q)
    store.questions.deactivate(q.question_id, reason="superseded")
    # No longer run-eligible, but still present as an inactive latest version.
    assert store.questions.approved_active() == []
    latest = store.questions.list()[0]
    assert latest.active is False


def test_response_insert_is_write_once(store):
    r = sample_response()
    store.responses.insert(r)
    assert store.responses.get(r.response_id) == r
    with pytest.raises(ValueError):
        store.responses.insert(r)  # immutable: re-insert refused


def test_scoring_add_version_increments_and_retains(store):
    store.responses.insert(sample_response())
    v1 = store.scores.add_version(sample_scoring())
    v2 = store.scores.add_version(sample_scoring())
    assert (v1.version, v2.version) == (1, 2)
    assert len(store.scores.versions_for("RESP-1")) == 2
    assert store.scores.latest_for("RESP-1").version == 2


def test_scoring_persists_competitor_sentiments(store):
    store.responses.insert(sample_response())
    record = sample_scoring().model_copy(update={"competitor_sentiments": {"rival": 0.7}})
    store.scores.add_version(record)
    assert store.scores.latest_for("RESP-1").competitor_sentiments == {"rival": 0.7}


def test_alert_list_orders_by_severity(store):
    store.responses.insert(sample_response())
    score = store.scores.add_version(sample_scoring())
    store.alerts.insert(sample_alert(score.score_id))
    alerts = store.alerts.list()
    assert len(alerts) == 1
    assert alerts[0].severity == 3


def test_run_lifecycle_create_checkpoint_finalize(store):
    run = store.runs.create(TriggerType.ADHOC)
    store.runs.checkpoint(run.run_id, "Q-PROS-1")
    assert store.runs.get(run.run_id).last_completed_question_id == "Q-PROS-1"

    finalized = store.runs.finalize(
        run.run_id,
        RunTotals(
            questions_attempted=3,
            responses_captured=3,
            failure_count=0,
            total_tokens=126,
            est_cost=0.01,
        ),
    )
    assert finalized.responses_captured == 3
    assert finalized.ended_at is not None
