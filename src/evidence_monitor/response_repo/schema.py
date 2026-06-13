"""The immutable Response record (Principle II — responses are immutable; scores are versioned).

A ``Response`` captures exactly one target's answer to one question in one run. Once written it
is never mutated: the Pydantic model is frozen, and the storage layer
(``response_repo/repository.py`` / the SQLite store) rejects any post-insert update. Derived
assessments live in a separate, versioned
:class:`~evidence_monitor.data_access.models.ScoringRecord`, linked by ``response_id``.

Brand / therapeutic-area / domain fields are denormalized here purely for queryability (FR-012);
they are carried as opaque data (Principle IV), not interpreted in logic.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from evidence_monitor.data_access.models import (
    Domain,
    FinishReason,
    Persona,
    ResponseStatus,
    _new_id,
    _utcnow,
)


class Response(BaseModel):
    """An immutable record of one (question × target × run) answer."""

    # ``frozen=True`` makes instances hashable and rejects attribute assignment;
    # ``extra="forbid"`` keeps the shape exact.
    model_config = ConfigDict(frozen=True, extra="forbid")

    response_id: str = Field(default_factory=_new_id)
    run_id: str
    question_id: str
    target_id: str
    timestamp_utc: datetime = Field(default_factory=_utcnow)

    # Captured at call time (Principle V — resolved from config, not hard-coded).
    llm_name: str
    llm_model_version: str

    # Denormalized question facets for queryability (FR-012) — opaque data only.
    persona: Persona
    therapeutic_area: str
    brand_focus: str
    domain: Domain

    # The full, unedited payload (DM-002 / FR-008).
    response_text: str
    response_tokens: int = 0
    finish_reason: FinishReason
    status: ResponseStatus
    block_reason: str | None = None  # populated when status is BLOCKED

    # Denormalized convenience flag maintained by the alert layer; never decided here.
    alert_triggered: bool = False

    created_at: datetime = Field(default_factory=_utcnow)


__all__ = ["Response"]
