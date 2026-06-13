"""Unit tests for entity schemas: enum surface, validation rules, no-PII shape."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from tests.fixtures import sample_questions, sample_scoring

from evidence_monitor.data_access.models import (
    ALERT_SEVERITY,
    Alert,
    AlertRule,
    ApprovalStatus,
    CitationStatus,
    CompetitivePosition,
    LLMTarget,
    Persona,
    Question,
    ScoringRecord,
)


def test_enums_expose_expected_members():
    assert {s.value for s in ApprovalStatus} == {"PENDING", "APPROVED", "REJECTED"}
    assert {p.value for p in Persona} == {"PROSPECT", "PROVIDER", "PATIENT"}
    assert {c.value for c in CitationStatus} == {
        "CITED",
        "PARTIAL",
        "ABSENT",
        "WRONG_INDICATION",
    }


def test_question_defaults_to_pending_and_not_run_eligible():
    q = sample_questions()[1]  # provider question, left PENDING
    assert q.approval_status is ApprovalStatus.PENDING
    assert q.run_eligible is False


def test_approved_active_question_is_run_eligible():
    q = sample_questions()[0]
    assert q.approval_status is ApprovalStatus.APPROVED
    assert q.active is True
    assert q.run_eligible is True


@pytest.mark.parametrize("score", [-1.0, 0.0, 1.0])
def test_sentiment_score_accepts_bounds(score):
    rec = sample_scoring().model_copy(update={"sentiment_score": score})
    assert rec.sentiment_score == score


@pytest.mark.parametrize("score", [-1.0001, 1.0001, 2.0, -5.0])
def test_sentiment_score_rejects_out_of_range(score):
    with pytest.raises(ValidationError):
        ScoringRecord(
            response_id="R",
            sentiment_score=score,
            competitive_position=CompetitivePosition.AMONG_OPTIONS,
            citation_status=CitationStatus.CITED,
            scoring_rationale="x",
            scorer_model="m",
        )


def test_key_claims_capped_at_five():
    with pytest.raises(ValidationError):
        ScoringRecord(
            response_id="R",
            sentiment_score=0.0,
            competitive_position=CompetitivePosition.AMONG_OPTIONS,
            citation_status=CitationStatus.CITED,
            key_claims=[f"claim {i}" for i in range(6)],
            scoring_rationale="x",
            scorer_model="m",
        )


def test_scoring_rationale_required_nonempty():
    with pytest.raises(ValidationError):
        ScoringRecord(
            response_id="R",
            sentiment_score=0.0,
            competitive_position=CompetitivePosition.AMONG_OPTIONS,
            citation_status=CitationStatus.CITED,
            scoring_rationale="",
            scorer_model="m",
        )


def test_extra_fields_forbidden_guards_against_pii_leak():
    # A stray PII-shaped field must be rejected, not silently stored (Principle III).
    with pytest.raises(ValidationError):
        Question(
            question_id="Q",
            question_text="generic",
            persona=Persona.PROSPECT,
            therapeutic_area="Area-One",
            brand_focus="Brand-X",
            domain="EFFICACY",
            patient_name="should not exist",
        )


def test_alert_for_rule_assigns_canonical_severity():
    alert = Alert.for_rule(
        score_id="S", response_id="R", rule=AlertRule.WRONG_INDICATION, reason="why"
    )
    assert alert.severity == ALERT_SEVERITY[AlertRule.WRONG_INDICATION]
    # WRONG_INDICATION is the highest severity (FR-021).
    assert alert.severity == max(ALERT_SEVERITY.values())


def test_target_persona_gating():
    provider_only = LLMTarget(
        target_id="oe",
        llm_name="oe",
        model_version="v1",
        personas=[Persona.PROVIDER],
    )
    assert provider_only.serves(Persona.PROVIDER) is True
    assert provider_only.serves(Persona.PATIENT) is False

    unconditional = LLMTarget(target_id="t", llm_name="t", model_version="v1", personas=[])
    assert unconditional.serves(Persona.PATIENT) is True
