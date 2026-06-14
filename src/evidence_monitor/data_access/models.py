"""Shared enumerations and entity schemas for the Evidence Monitoring Agent.

These Pydantic models are the canonical persisted shapes for every entity except
the immutable :class:`~evidence_monitor.response_repo.schema.Response`, which lives
in ``response_repo/schema.py`` to keep its write-once contract close to its writer.

Constitution alignment:
- **No PII/PHI** (Principle III): no field here holds personal data; tests assert it.
- **Content-agnostic code** (Principle IV): brand / competitor / indication values are
  plain ``str`` data carried *through* these models — never enumerated or hard-coded here.
- **Explain the score** (Principle VII): :class:`ScoringRecord` always carries
  ``brand_mentions``, ``key_claims`` (≤5), and a ``scoring_rationale``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utcnow() -> datetime:
    """Timezone-aware UTC now (used as a default factory)."""
    return datetime.now(UTC)


def _new_id() -> str:
    """Opaque UUID4 primary key as a string."""
    return str(uuid4())


# --------------------------------------------------------------------------- #
# Enumerations (data-model.md)
# --------------------------------------------------------------------------- #
class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Persona(StrEnum):
    """Question-authoring *style* tag — NOT a routing rule."""

    PROSPECT = "PROSPECT"
    PROVIDER = "PROVIDER"
    PATIENT = "PATIENT"


class Domain(StrEnum):
    EFFICACY = "EFFICACY"
    SAFETY = "SAFETY"
    ACCESS = "ACCESS"
    COMPARATIVE = "COMPARATIVE"
    GENERAL = "GENERAL"


class ResponseStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TRUNCATED = "TRUNCATED"
    BLOCKED = "BLOCKED"


class FinishReason(StrEnum):
    STOP = "STOP"
    LENGTH = "LENGTH"
    ERROR = "ERROR"
    SAFETY = "SAFETY"


class CompetitivePosition(StrEnum):
    FIRST_LINE_RECOMMENDED = "FIRST_LINE_RECOMMENDED"
    AMONG_OPTIONS = "AMONG_OPTIONS"
    SECOND_LINE = "SECOND_LINE"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"
    NOT_MENTIONED = "NOT_MENTIONED"


class CitationStatus(StrEnum):
    CITED = "CITED"
    PARTIAL = "PARTIAL"
    ABSENT = "ABSENT"
    WRONG_INDICATION = "WRONG_INDICATION"


class AlertRule(StrEnum):
    NEGATIVE_SENTIMENT = "NEGATIVE_SENTIMENT"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"
    COMPETITOR_HIGHER = "COMPETITOR_HIGHER"
    WRONG_INDICATION = "WRONG_INDICATION"


class TriggerType(StrEnum):
    SCHEDULED = "SCHEDULED"
    ADHOC = "ADHOC"


class AuditEventType(StrEnum):
    QUERY_DISPATCHED = "QUERY_DISPATCHED"
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
    RUN_STARTED = "RUN_STARTED"
    RUN_ENDED = "RUN_ENDED"
    ERROR = "ERROR"
    # Medical Affairs curation actions (US3) — auditable but not tied to a run.
    QUESTION_APPROVED = "QUESTION_APPROVED"
    QUESTION_REJECTED = "QUESTION_REJECTED"
    QUESTION_EDITED = "QUESTION_EDITED"


# Severity ordering for alerts — higher number = more severe. WRONG_INDICATION
# (a person routed to wrong-disease content) is reserved the highest severity (FR-021).
ALERT_SEVERITY: dict[AlertRule, int] = {
    AlertRule.NEGATIVE_SENTIMENT: 1,
    AlertRule.NOT_RECOMMENDED: 2,
    AlertRule.COMPETITOR_HIGHER: 2,
    AlertRule.WRONG_INDICATION: 3,
}


# --------------------------------------------------------------------------- #
# Entities
# --------------------------------------------------------------------------- #
class Question(BaseModel):
    """A curated, versioned question. Mutable only via new versions; never hard-deleted."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    version: int = 1
    question_text: str
    persona: Persona
    therapeutic_area: str
    brand_focus: str
    domain: Domain
    active: bool = True
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    approver_name: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @property
    def run_eligible(self) -> bool:
        """Only APPROVED *and* active questions are ever submitted (FR-003)."""
        return self.active and self.approval_status is ApprovalStatus.APPROVED


class LLMTarget(BaseModel):
    """A configured public model to monitor. Sourced from ``config/targets.yaml``."""

    model_config = ConfigDict(extra="forbid")

    target_id: str
    llm_name: str
    model_version: str
    endpoint: str | None = None
    temperature: float = 0.0
    max_tokens: int = 1024
    rpm_limit: int = 60
    tpm_limit: int = 90_000
    personas: list[Persona] = Field(default_factory=list)
    active: bool = True
    tos_acknowledged: bool = False

    def serves(self, persona: Persona) -> bool:
        """Whether this target receives the given persona's questions.

        An empty ``personas`` list means "all personas" (the default for the
        unconditional targets); a populated list restricts the target (e.g. Open
        Evidence = PROVIDER only).
        """
        return not self.personas or persona in self.personas


class Run(BaseModel):
    """A single scheduled or ad-hoc execution batch."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=_new_id)
    trigger_type: TriggerType = TriggerType.SCHEDULED
    started_at: datetime = Field(default_factory=_utcnow)
    ended_at: datetime | None = None
    questions_attempted: int = 0
    responses_captured: int = 0
    failure_count: int = 0
    total_tokens: int = 0
    est_cost: float = 0.0
    last_completed_question_id: str | None = None


class ScoringRecord(BaseModel):
    """A versioned, derived assessment of one Response. Links by ``response_id``;
    never mutates the response (Principle II)."""

    model_config = ConfigDict(extra="forbid")

    score_id: str = Field(default_factory=_new_id)
    response_id: str
    version: int = 1
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    competitive_position: CompetitivePosition
    citation_status: CitationStatus
    brand_mentions: list[str] = Field(default_factory=list)
    # Sentiment toward each detected COMPETITOR brand (brand → −1.0..+1.0). Distinct from
    # ``sentiment_score`` (toward OUR therapy); the deterministic COMPETITOR_HIGHER rule compares
    # the two. Empty when no competitor is detected. Brand names are opaque data (Principle IV).
    competitor_sentiments: dict[str, float] = Field(default_factory=dict)
    key_claims: list[str] = Field(default_factory=list)
    scoring_rationale: str = Field(min_length=1)
    scorer_model: str
    is_human_override: bool = False
    created_at: datetime = Field(default_factory=_utcnow)

    @field_validator("key_claims")
    @classmethod
    def _at_most_five_claims(cls, v: list[str]) -> list[str]:
        if len(v) > 5:
            raise ValueError("key_claims may contain at most 5 items")
        return v

    @field_validator("competitor_sentiments")
    @classmethod
    def _competitor_sentiments_in_range(cls, v: dict[str, float]) -> dict[str, float]:
        if any(not -1.0 <= score <= 1.0 for score in v.values()):
            raise ValueError("each competitor sentiment must be within -1.0..1.0")
        return v


class Alert(BaseModel):
    """A triggered flag linked to a ScoringRecord and Response."""

    model_config = ConfigDict(extra="forbid")

    alert_id: str = Field(default_factory=_new_id)
    score_id: str
    response_id: str
    rule_fired: AlertRule
    severity: int
    reason: str
    created_at: datetime = Field(default_factory=_utcnow)

    @classmethod
    def for_rule(cls, *, score_id: str, response_id: str, rule: AlertRule, reason: str) -> Alert:
        """Build an alert with the canonical severity for ``rule`` (FR-021)."""
        return cls(
            score_id=score_id,
            response_id=response_id,
            rule_fired=rule,
            severity=ALERT_SEVERITY[rule],
            reason=reason,
        )


class AuditEvent(BaseModel):
    """An append-only record of one external query/response or lifecycle event."""

    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(default_factory=_new_id)
    run_id: str
    event_type: AuditEventType
    role: str  # ORCHESTRATOR | TARGET
    target: str
    ts: datetime = Field(default_factory=_utcnow)
    http_status: int | None = None
    detail: str = ""  # MUST be non-secret


__all__ = [
    "ALERT_SEVERITY",
    "Alert",
    "AlertRule",
    "ApprovalStatus",
    "AuditEvent",
    "AuditEventType",
    "CitationStatus",
    "CompetitivePosition",
    "Domain",
    "FinishReason",
    "LLMTarget",
    "Persona",
    "Question",
    "ResponseStatus",
    "Run",
    "ScoringRecord",
    "TriggerType",
]
