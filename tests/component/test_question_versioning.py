"""Component tests for question versioning + soft-delete via QuestionService (US3, T057).

Operates on the real seed bank: editing a question appends a new version (history retained,
never hard-deleted) and deactivation soft-deletes (excluded from runs, still present as inactive).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.question_repo.importer import import_questions
from evidence_monitor.question_repo.repository import QuestionService

SEED_CSV = Path(__file__).resolve().parents[2] / "data" / "question_bank.csv"


@pytest.fixture
def service():
    store = SqliteStore(":memory:")
    import_questions(store.questions, SEED_CSV)
    yield QuestionService(store.questions), store
    store.close()


def _versions_on_disk(store: SqliteStore, question_id: str) -> int:
    return store.connection.execute(
        "SELECT COUNT(*) FROM questions WHERE question_id = ?", (question_id,)
    ).fetchone()[0]


def test_edit_creates_a_new_version_and_retains_history(service):
    svc, store = service
    qid = svc.list_questions()[0].question_id
    original = svc.get(qid)
    assert original.version == 1

    edited = svc.edit(qid, question_text="A revised, still-generic question?")

    assert edited.version == 2
    assert edited.question_text == "A revised, still-generic question?"
    assert svc.get(qid).question_text == edited.question_text  # latest wins
    # History retained: both versions persist; nothing is overwritten or deleted.
    assert _versions_on_disk(store, qid) == 2


def test_edit_unknown_question_raises(service):
    svc, _ = service
    with pytest.raises(KeyError):
        svc.edit("does-not-exist", question_text="x")


def test_deactivate_soft_deletes_and_excludes_from_runs(service):
    svc, store = service
    qid = svc.list_questions()[0].question_id
    svc.approve(qid, approver="ma_reviewer")
    assert any(q.question_id == qid for q in svc.run_eligible())  # eligible while active

    svc.deactivate(qid, reason="superseded by a newer phrasing")

    latest = svc.get(qid)
    assert latest.active is False
    # Excluded from the run-eligible set despite being APPROVED...
    assert all(q.question_id != qid for q in svc.run_eligible())
    # ...but never purged — the row is still queryable as an inactive latest version.
    assert _versions_on_disk(store, qid) == 3  # import → approve → deactivate
    assert svc.get(qid) is not None
