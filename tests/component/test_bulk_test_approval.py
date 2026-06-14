"""Component tests for the TEST-only bulk approval helpers (``approve-all-test-numbered`` /
``reset-to-pending``).

These are operator conveniences for a self-service test run — explicitly NOT the formal Medical
Affairs sign-off. They must still go through the repository approval seam and write to the audit
log (never raw SQL), assign ``approver-N`` / ``test-N`` in stable ``question_id`` order, be
idempotent (re-running reassigns the same N, no duplicate versions), re-stamp an existing real
approval, and reset cleanly back to PENDING.
"""

from __future__ import annotations

import pytest

from evidence_monitor.cli import cmd_approve_all_test_numbered, cmd_reset_to_pending
from evidence_monitor.data_access.models import (
    ApprovalStatus,
    AuditEventType,
    Domain,
    Persona,
    Question,
)
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.question_repo.repository import QuestionService


@pytest.fixture
def store():
    s = SqliteStore(":memory:")
    yield s
    s.close()


def _seed(store: SqliteStore, n: int = 5) -> None:
    """Insert ``n`` generic PENDING questions with stable, zero-padded ids (content-agnostic)."""
    for i in range(1, n + 1):
        store.questions.upsert(
            Question(
                question_id=f"Q-{i:03d}",
                question_text=f"Generic question {i}?",
                persona=Persona.PROSPECT,
                therapeutic_area="Area-One",
                brand_focus="Brand-X",
                domain=Domain.EFFICACY,
            )
        )


def _latest(store: SqliteStore) -> list[Question]:
    return sorted(QuestionService(store.questions).list_questions(), key=lambda q: q.question_id)


def _max_version(store: SqliteStore, qid: str) -> int:
    return store.connection.execute(
        "SELECT MAX(version) FROM questions WHERE question_id = ?", (qid,)
    ).fetchone()[0]


def _audit_count(store: SqliteStore, event_type: AuditEventType) -> int:
    return store.connection.execute(
        "SELECT COUNT(*) FROM audit_log WHERE event_type = ?", (str(event_type),)
    ).fetchone()[0]


# --------------------------------------------------------------------------- #
# approve-all-test-numbered
# --------------------------------------------------------------------------- #
def test_numbers_every_active_question_in_question_id_order(store):
    _seed(store, 5)
    count, first3, last3 = cmd_approve_all_test_numbered(store)

    assert count == 5
    assert first3[0] == ("Q-001", "approver-1", "test-1")
    assert last3[-1] == ("Q-005", "approver-5", "test-5")
    # Every active question is APPROVED with the N matching its sorted position.
    for n, q in enumerate(_latest(store), start=1):
        assert q.approval_status is ApprovalStatus.APPROVED
        assert q.approver_name == f"approver-{n}"
        assert q.approval_note == f"test-{n}"


def test_writes_one_audit_entry_per_approval(store):
    _seed(store, 5)
    cmd_approve_all_test_numbered(store)
    assert _audit_count(store, AuditEventType.QUESTION_APPROVED) == 5


def test_is_idempotent_no_duplicate_versions_on_rerun(store):
    _seed(store, 4)
    cmd_approve_all_test_numbered(store)
    versions_after_first = {
        q.question_id: _max_version(store, q.question_id) for q in _latest(store)
    }

    count, _, _ = cmd_approve_all_test_numbered(store)  # re-run

    assert count == 4
    # No question gained a new version, and no extra audit rows were written.
    for q in _latest(store):
        assert _max_version(store, q.question_id) == versions_after_first[q.question_id]
    assert _audit_count(store, AuditEventType.QUESTION_APPROVED) == 4


def test_restamps_a_question_already_approved_by_a_real_reviewer(store):
    _seed(store, 3)
    # Q-002 is already APPROVED by a real MA reviewer (the forward-only gate would no-op on it).
    store.questions.set_approval("Q-002", ApprovalStatus.APPROVED, "ma_reviewer")

    cmd_approve_all_test_numbered(store)

    q2 = store.questions.get("Q-002")
    assert q2.approver_name == "approver-2"  # re-stamped to the numbered approver
    assert q2.approval_note == "test-2"


# --------------------------------------------------------------------------- #
# reset-to-pending
# --------------------------------------------------------------------------- #
def test_reset_clears_status_approver_and_note(store):
    _seed(store, 5)
    cmd_approve_all_test_numbered(store)

    changed = cmd_reset_to_pending(store)

    assert changed == 5
    for q in _latest(store):
        assert q.approval_status is ApprovalStatus.PENDING
        assert q.approver_name is None
        assert q.approval_note is None
    assert store.questions.approved_active() == []
    assert _audit_count(store, AuditEventType.QUESTION_EDITED) == 5


def test_reset_is_idempotent_on_already_pending(store):
    _seed(store, 3)  # all start PENDING with no approver/note
    changed = cmd_reset_to_pending(store)
    assert changed == 0  # nothing to do
    assert _audit_count(store, AuditEventType.QUESTION_EDITED) == 0


def test_approve_then_reset_round_trips(store):
    _seed(store, 4)
    cmd_approve_all_test_numbered(store)
    cmd_reset_to_pending(store)
    cmd_approve_all_test_numbered(store)  # approve again after reset

    approved = store.questions.approved_active()
    assert len(approved) == 4
    for n, q in enumerate(sorted(approved, key=lambda q: q.question_id), start=1):
        assert q.approver_name == f"approver-{n}"
        assert q.approval_note == f"test-{n}"
