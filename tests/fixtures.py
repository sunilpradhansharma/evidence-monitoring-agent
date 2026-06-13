"""Tiny, synthetic in-memory fixtures for Foundational-phase tests.

A handful of rows only — enough to exercise the schemas, the store, and the audit writer. The
real curated question bank is imported later (Impl-3); nothing here is hard-coded business data.
All values are deliberately generic placeholders (``Therapy-A``, ``Brand-X``) so the fixtures
carry **no PII/PHI and no real drug/competitor/indication names** (Principles III & IV).
"""

from __future__ import annotations

from evidence_monitor.data_access.models import (
    Alert,
    AlertRule,
    ApprovalStatus,
    AuditEvent,
    AuditEventType,
    CitationStatus,
    CompetitivePosition,
    Domain,
    LLMTarget,
    Persona,
    Question,
    Run,
    ScoringRecord,
    TriggerType,
)
from evidence_monitor.response_repo.schema import FinishReason, Response, ResponseStatus

# Generic placeholder content — NOT real therapies/brands.
_THERAPY = "Therapy-A"
_BRAND = "Brand-X"


def sample_questions() -> list[Question]:
    """Three generic questions, one per persona, across two therapeutic areas."""
    return [
        Question(
            question_id="Q-PROS-1",
            question_text="What treatment options exist for this generic condition?",
            persona=Persona.PROSPECT,
            therapeutic_area="Area-One",
            brand_focus=_BRAND,
            domain=Domain.EFFICACY,
            approval_status=ApprovalStatus.APPROVED,
            approver_name="ma_reviewer",
        ),
        Question(
            question_id="Q-PROV-1",
            question_text="What dosing guidance applies for this generic indication?",
            persona=Persona.PROVIDER,
            therapeutic_area="Area-One",
            brand_focus=_BRAND,
            domain=Domain.SAFETY,
        ),
        Question(
            question_id="Q-PAT-1",
            question_text="Is there a more affordable option for this generic therapy?",
            persona=Persona.PATIENT,
            therapeutic_area="Area-Two",
            brand_focus=_THERAPY,
            domain=Domain.ACCESS,
        ),
    ]


def sample_target() -> LLMTarget:
    return LLMTarget(
        target_id="provider-a",
        llm_name="provider-a",
        model_version="provider-a-model-1",
        personas=[Persona.PROSPECT, Persona.PROVIDER, Persona.PATIENT],
        tos_acknowledged=True,
    )


def sample_run() -> Run:
    return Run(run_id="RUN-1", trigger_type=TriggerType.ADHOC)


def sample_response(run_id: str = "RUN-1", question_id: str = "Q-PROS-1") -> Response:
    return Response(
        response_id="RESP-1",
        run_id=run_id,
        question_id=question_id,
        target_id="provider-a",
        llm_name="provider-a",
        llm_model_version="provider-a-model-1",
        persona=Persona.PROSPECT,
        therapeutic_area="Area-One",
        brand_focus=_BRAND,
        domain=Domain.EFFICACY,
        response_text="A generic, non-PII answer about treatment options.",
        response_tokens=42,
        finish_reason=FinishReason.STOP,
        status=ResponseStatus.SUCCESS,
    )


def sample_scoring(response_id: str = "RESP-1") -> ScoringRecord:
    return ScoringRecord(
        response_id=response_id,
        sentiment_score=0.4,
        competitive_position=CompetitivePosition.AMONG_OPTIONS,
        citation_status=CitationStatus.CITED,
        brand_mentions=[_BRAND],
        key_claims=["Generic claim one.", "Generic claim two."],
        scoring_rationale="Balanced mention with positive framing.",
        scorer_model="scorer-model-1",
    )


def sample_alert(score_id: str, response_id: str = "RESP-1") -> Alert:
    return Alert.for_rule(
        score_id=score_id,
        response_id=response_id,
        rule=AlertRule.WRONG_INDICATION,
        reason="Routed to wrong-indication content.",
    )


def sample_audit_events(run_id: str = "RUN-1") -> list[AuditEvent]:
    return [
        AuditEvent(
            run_id=run_id,
            event_type=AuditEventType.RUN_STARTED,
            role="ORCHESTRATOR",
            target="run",
            detail="run started",
        ),
        AuditEvent(
            run_id=run_id,
            event_type=AuditEventType.QUERY_DISPATCHED,
            role="TARGET",
            target="provider-a:Q-PROS-1",
            http_status=200,
            detail="dispatched",
        ),
        AuditEvent(
            run_id=run_id,
            event_type=AuditEventType.RESPONSE_RECEIVED,
            role="TARGET",
            target="provider-a:Q-PROS-1",
            http_status=200,
            detail="received",
        ),
    ]
