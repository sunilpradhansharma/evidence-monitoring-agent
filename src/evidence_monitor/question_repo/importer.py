"""CSV / Excel importer for the Question Repository (US3, FR-005).

Imports a curated question bank into the repository with two firm rules:

- **Everything imports as PENDING.** Eligibility is granted later through the approval gate
  (Principle I); import never approves anything.
- **Idempotent upsert by ``question_id``.** Re-importing an unchanged file creates NO new
  versions (skipped). A row whose *content* changed appends a new version (back to PENDING, so
  edited content is re-curated); an unseen ``question_id`` is created at version 1.

Content equality deliberately ignores ``approval_status``/``approver`` so a re-import never
clobbers a Medical Affairs decision on otherwise-unchanged content.

Content-agnostic (Principle IV): persona/domain are structural enums; brand, therapeutic area,
and indication text are carried as opaque data — this module hard-codes none of them.
"""

from __future__ import annotations

import csv
from collections import Counter, OrderedDict
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from evidence_monitor.data_access.interface import QuestionRepository
from evidence_monitor.data_access.models import ApprovalStatus, Domain, Persona, Question

_REQUIRED_COLUMNS = frozenset(
    {"question_id", "persona", "therapeutic_area", "brand_focus", "domain", "question_text"}
)
_TRUE = frozenset({"1", "true", "yes", "y", "t"})


@dataclass(frozen=True)
class ImportReport:
    """Outcome of an import: per-disposition counts plus a tally of the bank by dimension."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    by_persona: dict[str, int] = field(default_factory=dict)
    by_therapeutic_area: dict[str, int] = field(default_factory=dict)
    dry_run: bool = False

    @property
    def processed(self) -> int:
        """Distinct ``question_id``s seen in the file."""
        return self.created + self.updated + self.skipped


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _parse_bool(value: object, *, default: bool = True) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in _TRUE


def _row_to_question(row: dict[str, object]) -> Question:
    """Map one source row to a PENDING :class:`Question` (approval is granted later, not here)."""
    return Question(
        question_id=str(row["question_id"]).strip(),
        question_text=str(row["question_text"]).strip(),
        persona=Persona(str(row["persona"]).strip().upper()),
        therapeutic_area=str(row["therapeutic_area"]).strip(),
        brand_focus=str(row["brand_focus"]).strip(),
        domain=Domain(str(row["domain"]).strip().upper()),
        active=_parse_bool(row.get("active")),
        approval_status=ApprovalStatus.PENDING,
    )


def _read_csv(path: Path) -> Iterator[dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as fh:
        yield from csv.DictReader(fh)


def _read_excel(path: Path) -> Iterator[dict[str, object]]:
    try:
        import openpyxl  # imported lazily so CSV import needs no Excel dependency
    except ImportError as exc:  # pragma: no cover - exercised only without openpyxl
        raise ImportError(
            "Excel import requires the 'openpyxl' package; install it or import a CSV instead."
        ) from exc
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    try:
        header = [str(c).strip() if c is not None else "" for c in next(rows)]
    except StopIteration:
        return
    for raw in rows:
        if all(cell is None for cell in raw):
            continue
        yield dict(zip(header, raw, strict=False))


def _load_rows(path: Path) -> list[dict[str, object]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        rows = list(_read_csv(path))
    elif suffix in {".xlsx", ".xlsm", ".xls"}:
        rows = list(_read_excel(path))
    else:
        raise ValueError(
            f"unsupported question-bank file type: {path.suffix!r} (use .csv or .xlsx)"
        )
    if rows:
        missing = _REQUIRED_COLUMNS - set(rows[0].keys())
        if missing:
            raise ValueError(f"question bank is missing required columns: {sorted(missing)}")
    return rows


def _content_key(q: Question) -> tuple[object, ...]:
    """Fields that define a question's content (approval state intentionally excluded)."""
    return (q.question_text, q.persona, q.therapeutic_area, q.brand_focus, q.domain, q.active)


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #
def import_questions(
    repo: QuestionRepository,
    file_path: str | Path,
    *,
    dry_run: bool = False,
) -> ImportReport:
    """Idempotently import a CSV/Excel question bank as PENDING. Returns a counts report.

    ``dry_run`` computes the report without writing anything.
    """
    path = Path(file_path)
    # Dedupe within the file by question_id (last row wins) so counts and writes agree.
    parsed: OrderedDict[str, Question] = OrderedDict()
    for row in _load_rows(path):
        question = _row_to_question(row)
        parsed[question.question_id] = question

    created = updated = skipped = 0
    for question in parsed.values():
        existing = repo.get(question.question_id)
        if existing is None:
            if not dry_run:
                repo.upsert(question)
            created += 1
        elif _content_key(existing) == _content_key(question):
            skipped += 1
        else:
            if not dry_run:
                repo.upsert(question)
            updated += 1

    by_persona = Counter(str(q.persona) for q in parsed.values())
    by_area = Counter(q.therapeutic_area for q in parsed.values())
    return ImportReport(
        created=created,
        updated=updated,
        skipped=skipped,
        by_persona=dict(sorted(by_persona.items())),
        by_therapeutic_area=dict(sorted(by_area.items())),
        dry_run=dry_run,
    )


__all__ = ["ImportReport", "import_questions"]
