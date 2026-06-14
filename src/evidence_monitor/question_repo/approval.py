"""Approval gate for the Question Repository (US3, Principle I — Human approves, system suggests).

A deterministic state machine over ``approval_status``. Only Medical Affairs moves a question
between states, and every transition is recorded as a NEW version (history retained) with the
approver's name. The allowed transitions mirror data-model.md:

    PENDING  → APPROVED   (approver recorded)
    PENDING  → REJECTED
    APPROVED → REJECTED
    REJECTED → ∅          (terminal — never leaves REJECTED)

Re-asserting the current state is an idempotent no-op (no new version). Any other move raises
:class:`ApprovalError`. Approval logic lives in code, never in the model (Principle VIII).
"""

from __future__ import annotations

from evidence_monitor.data_access.interface import QuestionRepository
from evidence_monitor.data_access.models import (
    ApprovalStatus,
    AuditEvent,
    AuditEventType,
    Question,
)

# Curation actions are auditable (Principle II) but happen outside any run, so they carry a
# sentinel, non-secret run id rather than a real ``run_id``.
APPROVAL_AUDIT_RUN_ID = "approvals"

# Allowed forward transitions. REJECTED is terminal (empty set).
_ALLOWED: dict[ApprovalStatus, set[ApprovalStatus]] = {
    ApprovalStatus.PENDING: {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED},
    ApprovalStatus.APPROVED: {ApprovalStatus.REJECTED},
    ApprovalStatus.REJECTED: set(),
}


class ApprovalError(ValueError):
    """Raised on a disallowed approval transition or a missing approver."""


def _transition(
    repo: QuestionRepository,
    question_id: str,
    target: ApprovalStatus,
    approver: str,
    reason: str | None = None,
) -> Question:
    if not approver or not approver.strip():
        raise ApprovalError("an approver name is required to change approval status")
    current = repo.get(question_id)
    if current is None:
        raise KeyError(f"unknown question_id: {question_id}")
    if current.approval_status is target:
        return current  # idempotent: no redundant version
    if target not in _ALLOWED[current.approval_status]:
        raise ApprovalError(
            f"cannot move question {question_id} from {current.approval_status} to {target}"
        )
    return repo.set_approval(question_id, target, approver.strip(), reason)


def approve(repo: QuestionRepository, question_id: str, approver: str) -> Question:
    """Transition a PENDING question to APPROVED, recording ``approver`` (FR-002)."""
    return _transition(repo, question_id, ApprovalStatus.APPROVED, approver)


def reject(
    repo: QuestionRepository,
    question_id: str,
    approver: str,
    reason: str | None = None,
) -> Question:
    """Transition a PENDING or APPROVED question to REJECTED (terminal for runs)."""
    return _transition(repo, question_id, ApprovalStatus.REJECTED, approver, reason)


def approval_audit_event(
    *,
    event_type: AuditEventType,
    question_id: str,
    approver: str,
    reason: str | None = None,
) -> AuditEvent:
    """Build the append-only audit entry for one curation action (approve / reject / edit).

    ``detail`` is a short, non-secret sentence; the approver name is operator-supplied curation
    metadata (SE-002), not a credential, so it is recorded for the compliance trail.
    """
    verb = {
        AuditEventType.QUESTION_APPROVED: "approved",
        AuditEventType.QUESTION_REJECTED: "rejected",
        AuditEventType.QUESTION_EDITED: "edited",
    }[event_type]
    detail = f"{approver} {verb} question {question_id}"
    if reason:
        detail = f"{detail}: {reason}"
    return AuditEvent(
        run_id=APPROVAL_AUDIT_RUN_ID,
        event_type=event_type,
        role="MEDICAL_AFFAIRS",
        target=question_id,
        detail=detail,
    )


__all__ = [
    "APPROVAL_AUDIT_RUN_ID",
    "ApprovalError",
    "approval_audit_event",
    "approve",
    "reject",
]
