"""Component tests for the CSV importer against the real seed question bank (US3, T061).

Exercises the importer end-to-end over ``data/question_bank.csv``: import as PENDING, the
per-persona / per-therapeutic-area tally (SC-004 minimums), and — critically — that a second
import of the same file creates no duplicates and no new versions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evidence_monitor.data_access.models import ApprovalStatus, Persona
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.question_repo.importer import import_questions

# repo-root/data/question_bank.csv  (tests/component/<file> → parents[2] == repo root)
SEED_CSV = Path(__file__).resolve().parents[2] / "data" / "question_bank.csv"


@pytest.fixture
def store():
    s = SqliteStore(":memory:")
    yield s
    s.close()


def _question_row_count(store: SqliteStore) -> int:
    return store.connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0]


def test_seed_csv_is_present():
    assert SEED_CSV.exists(), f"expected seed question bank at {SEED_CSV}"


def test_import_creates_all_questions_as_pending(store):
    report = import_questions(store.questions, SEED_CSV)

    assert report.created == report.processed  # every row was new
    assert report.updated == 0
    assert report.skipped == 0
    # Every imported question is PENDING — import never approves (Principle I).
    assert store.questions.list(approval_status=ApprovalStatus.APPROVED) == []
    assert len(store.questions.list(approval_status=ApprovalStatus.PENDING)) == report.processed


def test_import_meets_sc004_minimums(store):
    report = import_questions(store.questions, SEED_CSV)

    # ≥30 questions per persona (SC-004).
    for persona in (Persona.PROSPECT, Persona.PROVIDER, Persona.PATIENT):
        assert report.by_persona.get(str(persona), 0) >= 30, report.by_persona

    # Spans the three expected therapeutic areas (≥2 required by SC-004).
    assert {"Immunology", "Oncology", "Neuroscience"} <= set(report.by_therapeutic_area)


def test_reimport_is_idempotent_no_duplicates(store):
    first = import_questions(store.questions, SEED_CSV)
    rows_after_first = _question_row_count(store)

    second = import_questions(store.questions, SEED_CSV)

    # Nothing created or updated the second time; everything is skipped.
    assert second.created == 0
    assert second.updated == 0
    assert second.skipped == first.processed
    # No new versions were written — the row count is unchanged.
    assert _question_row_count(store) == rows_after_first
    # The run-eligible set is still empty (all PENDING); no silent duplication.
    assert store.questions.list(active=True) and len(store.questions.list()) == first.processed


def test_dry_run_writes_nothing(store):
    report = import_questions(store.questions, SEED_CSV, dry_run=True)

    assert report.dry_run is True
    assert report.created == report.processed
    assert _question_row_count(store) == 0  # nothing persisted
