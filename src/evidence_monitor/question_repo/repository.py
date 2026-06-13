"""Question Repository — the Medical Affairs curation domain layer (US3).

A thin domain service over the ``data_access`` :class:`QuestionRepository` seam (Principle X):
core code depends on the protocol, never on SQLite. It adds curation semantics the raw store
does not — partial :meth:`edit` (load-latest → apply → new version) and convenience approval
delegation — while preserving the store's guarantees:

- **Versioning, never hard-delete** — every edit/approval/deactivation appends a new version;
  history is retained (FR-001).
- **Soft-delete** — :meth:`deactivate` flips ``active`` with a reason; rows are never purged.
- **Run eligibility** — :meth:`run_eligible` returns ONLY ``APPROVED`` + ``active`` questions
  (FR-003); nothing else is ever submitted.

Content-agnostic (Principle IV): brand / therapeutic-area / indication values flow through as
opaque ``str`` data — this module enumerates none of them.
"""

from __future__ import annotations

from evidence_monitor.data_access.interface import QuestionRepository
from evidence_monitor.data_access.models import ApprovalStatus, Persona, Question
from evidence_monitor.question_repo import approval


class QuestionService:
    """Curation operations over a :class:`QuestionRepository` (the data-access seam)."""

    def __init__(self, repo: QuestionRepository) -> None:
        self._repo = repo

    # --- create / read ----------------------------------------------------- #
    def add(self, question: Question) -> Question:
        """Add a question (version 1). New questions default to ``PENDING`` (FR-002)."""
        return self._repo.upsert(question)

    def get(self, question_id: str) -> Question | None:
        """The latest version of one question, or ``None`` if unknown."""
        return self._repo.get(question_id)

    def list_questions(
        self,
        *,
        approval_status: ApprovalStatus | None = None,
        active: bool | None = None,
        persona: Persona | None = None,
        therapeutic_area: str | None = None,
    ) -> list[Question]:
        """Latest version of each question, optionally filtered."""
        return self._repo.list(
            approval_status=approval_status,
            active=active,
            persona=persona,
            therapeutic_area=therapeutic_area,
        )

    # --- edit (records a new version) -------------------------------------- #
    def edit(self, question_id: str, **changes: object) -> Question:
        """Apply field changes to the latest version, storing the result as a NEW version.

        The prior version is retained (FR-001); the edit is re-validated through the
        :class:`Question` model so an invalid change is rejected before it is stored.
        """
        current = self._repo.get(question_id)
        if current is None:
            raise KeyError(f"unknown question_id: {question_id}")
        updated = Question.model_validate({**current.model_dump(), **changes})
        return self._repo.upsert(updated)

    # --- soft-delete ------------------------------------------------------- #
    def deactivate(self, question_id: str, reason: str) -> Question:
        """Soft-delete: append an inactive version with a reason; never physically purge."""
        return self._repo.deactivate(question_id, reason)

    # --- approval gate (delegates to approval.py) -------------------------- #
    def approve(self, question_id: str, approver: str) -> Question:
        """Move a question to ``APPROVED``, recording the approver (FR-002)."""
        return approval.approve(self._repo, question_id, approver)

    def reject(self, question_id: str, approver: str, reason: str | None = None) -> Question:
        """Move a question to ``REJECTED`` (terminal for runs)."""
        return approval.reject(self._repo, question_id, approver, reason)

    # --- run eligibility --------------------------------------------------- #
    def run_eligible(self) -> list[Question]:
        """The submit set: APPROVED *and* active only (FR-003). Code, not the model, gates this."""
        return self._repo.approved_active()


__all__ = ["QuestionService"]
