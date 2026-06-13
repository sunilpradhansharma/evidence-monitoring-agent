"""Component tests for the importer against the real seed question bank (US3, T061).

Exercises the importer end-to-end over ``data/question_bank.csv``: import as PENDING, the
per-persona / per-therapeutic-area tally (SC-004 minimums), and — critically — that a second
import of the same file creates no duplicates and no new versions. A final round-trip test
covers the Excel (``.xlsx``) read path with generic, content-agnostic rows.
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

    # Spans at least two therapeutic areas (SC-004) — assert the count, not the names, so the
    # test stays content-agnostic; therapeutic-area names live only in data (Principle IV).
    assert len(report.by_therapeutic_area) >= 2, report.by_therapeutic_area


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


# --------------------------------------------------------------------------- #
# Excel (.xlsx) round-trip — generic, content-agnostic rows (no PII, no real brands)
# --------------------------------------------------------------------------- #
_XLSX_HEADER = [
    "question_id",
    "persona",
    "therapeutic_area",
    "brand_focus",
    "domain",
    "active",
    "question_text",
]
_XLSX_ROWS = [
    [
        "XL-PROS-1",
        "Prospect",
        "Area-One",
        "Brand-X",
        "Efficacy",
        "true",
        "A generic prospect question?",
    ],
    [
        "XL-PROV-1",
        "Provider",
        "Area-One",
        "Brand-X",
        "Safety",
        "true",
        "A generic provider question?",
    ],
    ["XL-PAT-1", "Patient", "Area-Two", "Brand-Y", "Access", "true", "A generic patient question?"],
]


def _write_xlsx(path: Path) -> Path:
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(_XLSX_HEADER)
    for row in _XLSX_ROWS:
        sheet.append(row)
    workbook.save(path)
    return path


def test_excel_round_trip_imports_as_pending(store, tmp_path):
    xlsx = _write_xlsx(tmp_path / "bank.xlsx")

    report = import_questions(store.questions, xlsx)

    assert report.created == len(_XLSX_ROWS)
    assert report.skipped == 0
    assert report.dry_run is False
    # Every imported question is PENDING, with the dimensions read back from the sheet.
    pending = store.questions.list(approval_status=ApprovalStatus.PENDING)
    assert {q.question_id for q in pending} == {"XL-PROS-1", "XL-PROV-1", "XL-PAT-1"}
    assert report.by_persona == {"PATIENT": 1, "PROSPECT": 1, "PROVIDER": 1}
    assert report.by_therapeutic_area == {"Area-One": 2, "Area-Two": 1}
    prospect = store.questions.get("XL-PROS-1")
    assert prospect.persona is Persona.PROSPECT
    assert prospect.brand_focus == "Brand-X"
    assert prospect.active is True


def test_excel_reimport_is_idempotent(store, tmp_path):
    xlsx = _write_xlsx(tmp_path / "bank.xlsx")
    import_questions(store.questions, xlsx)
    rows_after_first = _question_row_count(store)

    second = import_questions(store.questions, xlsx)

    assert second.created == 0
    assert second.skipped == len(_XLSX_ROWS)  # unchanged content → no new versions
    assert _question_row_count(store) == rows_after_first
