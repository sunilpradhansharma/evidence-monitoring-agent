"""The data-access seam (Principle X).

Core modules depend ONLY on the protocols and value objects defined here — never on a concrete
store. The local POC binds these to SQLite (``sqlite_store.py``); production swaps to
Aurora/DynamoDB behind the same protocols by config/implementation only, with no change to core
logic.

The protocols are ``runtime_checkable`` so tests can assert a concrete store satisfies the
surface. They intentionally describe *behaviour guarantees* the implementation must honour:

- **Immutability** — :meth:`ResponseRepository.insert` is write-once; updates raise.
- **Versioning** — :meth:`ScoringRepository.add_version` and :meth:`QuestionRepository.upsert`
  retain history instead of overwriting.
- **Append-only audit** — :class:`AuditWriter` exposes no mutation.
- **Soft-delete / retention** — deletes mark inactive with a reason; nothing is physically purged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, Protocol, TypeVar, runtime_checkable

from evidence_monitor.data_access.models import (
    Alert,
    ApprovalStatus,
    AuditEvent,
    Persona,
    Question,
    ResponseStatus,
    Run,
    ScoringRecord,
    TriggerType,
)
from evidence_monitor.response_repo.schema import Response

T = TypeVar("T")


# --------------------------------------------------------------------------- #
# Value objects
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RunTotals:
    """Aggregate counters written when a run is finalized."""

    questions_attempted: int
    responses_captured: int
    failure_count: int
    total_tokens: int
    est_cost: float
    ended_at: datetime | None = None


@dataclass(frozen=True)
class QueryFilters:
    """Any combination of response query dimensions (FR-012).

    Every field is optional; an unset field does not constrain the query.
    Exports (CSV/JSON) consume this same object so a view and its export match.
    """

    llm: str | None = None
    persona: Persona | None = None
    therapeutic_area: str | None = None
    brand: str | None = None
    domain: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    sentiment_min: float | None = None
    sentiment_max: float | None = None
    alert_status: bool | None = None
    status: ResponseStatus | None = None


@dataclass(frozen=True)
class Page(Generic[T]):
    """A paginated slice plus the total matching count (for pagination controls)."""

    items: list[T] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50


# --------------------------------------------------------------------------- #
# Repository protocols
# --------------------------------------------------------------------------- #
@runtime_checkable
class QuestionRepository(Protocol):
    def upsert(self, q: Question) -> Question:
        """Insert a question or record a new version on edit; never hard-delete."""
        ...

    def get(self, question_id: str) -> Question | None:
        """The latest version of one question, or ``None`` if unknown.

        Read-by-id underpins idempotent import (upsert-by-``question_id``) and editing.
        """
        ...

    def set_approval(
        self,
        question_id: str,
        status: ApprovalStatus,
        approver: str,
        reason: str | None = None,
    ) -> Question: ...

    def list(
        self,
        *,
        approval_status: ApprovalStatus | None = None,
        active: bool | None = None,
        persona: Persona | None = None,
        therapeutic_area: str | None = None,
    ) -> list[Question]: ...

    def approved_active(self) -> list[Question]:
        """The run-eligible set: APPROVED *and* active (FR-003)."""
        ...

    def deactivate(self, question_id: str, reason: str) -> Question:
        """Soft-delete: append an inactive version with a reason; never physically purge."""
        ...


@runtime_checkable
class ResponseRepository(Protocol):
    def insert(self, r: Response) -> Response:
        """Write-once. MUST raise on any attempt to overwrite an existing response."""
        ...

    def get(self, response_id: str) -> Response | None: ...

    def query(
        self, filters: QueryFilters, *, page: int = 1, page_size: int | None = 50
    ) -> Page[Response]:
        """Filtered, paginated reads across every query dimension (FR-012).

        ``page_size=None`` returns all matching rows in one page (used by exports so a view and
        its export match). Sentiment filters read the response's *latest* scoring version; a
        response with no score is excluded when a sentiment bound is set.
        """
        ...


@runtime_checkable
class ScoringRepository(Protocol):
    def add_version(self, s: ScoringRecord) -> ScoringRecord:
        """Append a new scoring version for a response; never mutates the response."""
        ...

    def latest_for(self, response_id: str) -> ScoringRecord | None: ...

    def versions_for(self, response_id: str) -> list[ScoringRecord]: ...


@runtime_checkable
class AlertRepository(Protocol):
    def insert(self, a: Alert) -> Alert: ...

    def list(self, *, order_by_severity: bool = True) -> list[Alert]: ...


@runtime_checkable
class RunRepository(Protocol):
    def create(self, trigger: TriggerType) -> Run: ...

    def checkpoint(self, run_id: str, last_completed_question_id: str) -> None:
        """Persist the resume point after each question completes (Principle IX)."""
        ...

    def finalize(self, run_id: str, totals: RunTotals) -> Run: ...

    def get(self, run_id: str) -> Run | None: ...


@runtime_checkable
class AuditWriter(Protocol):
    def append(self, event: AuditEvent) -> None:
        """Append-only: the protocol exposes no update or delete (Principle II)."""
        ...


@runtime_checkable
class DataAccess(Protocol):
    """Facade bundling every repository — the single object core code is handed."""

    questions: QuestionRepository
    responses: ResponseRepository
    scores: ScoringRepository
    alerts: AlertRepository
    runs: RunRepository
    audit: AuditWriter

    def close(self) -> None: ...


__all__ = [
    "AlertRepository",
    "AuditWriter",
    "DataAccess",
    "Page",
    "QueryFilters",
    "QuestionRepository",
    "ResponseRepository",
    "RunRepository",
    "RunTotals",
    "ScoringRepository",
]
