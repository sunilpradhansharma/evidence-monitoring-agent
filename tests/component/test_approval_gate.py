"""Component tests for the approval gate (US3, T059).

The authoritative eligibility rule: ONLY APPROVED + active questions are ever run-eligible
(FR-003). Imported questions start PENDING; approval/rejection are recorded as new versions with
the approver, and REJECTED is terminal.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evidence_monitor.data_access.models import ApprovalStatus
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.question_repo.approval import ApprovalError
from evidence_monitor.question_repo.importer import import_questions
from evidence_monitor.question_repo.repository import QuestionService

SEED_CSV = Path(__file__).resolve().parents[2] / "data" / "question_bank.csv"


@pytest.fixture
def service():
    store = SqliteStore(":memory:")
    import_questions(store.questions, SEED_CSV)
    yield QuestionService(store.questions)
    store.close()


def test_imported_questions_start_ineligible(service):
    # Everything imports PENDING → nothing is run-eligible yet (Principle I).
    assert service.run_eligible() == []


def test_only_approved_active_questions_are_selectable(service):
    ids = [q.question_id for q in service.list_questions()]
    approved_id, rejected_id, untouched_id = ids[0], ids[1], ids[2]

    approved = service.approve(approved_id, approver="ma_reviewer")
    assert approved.approval_status is ApprovalStatus.APPROVED
    assert approved.approver_name == "ma_reviewer"
    assert approved.version == 2  # transition recorded as a new version

    service.reject(rejected_id, approver="ma_reviewer", reason="off-label phrasing")

    eligible_ids = {q.question_id for q in service.run_eligible()}
    assert eligible_ids == {approved_id}  # only the APPROVED one
    assert rejected_id not in eligible_ids
    assert untouched_id not in eligible_ids  # still PENDING


def test_rejected_is_terminal(service):
    qid = service.list_questions()[0].question_id
    service.reject(qid, approver="ma_reviewer")
    with pytest.raises(ApprovalError):
        service.approve(qid, approver="ma_reviewer")  # cannot leave REJECTED


def test_approver_name_is_required(service):
    qid = service.list_questions()[0].question_id
    with pytest.raises(ApprovalError):
        service.approve(qid, approver="   ")


def test_reapproving_is_idempotent_no_new_version(service):
    qid = service.list_questions()[0].question_id
    service.approve(qid, approver="ma_reviewer")
    again = service.approve(qid, approver="ma_reviewer")
    assert again.version == 2  # unchanged — no redundant version written
