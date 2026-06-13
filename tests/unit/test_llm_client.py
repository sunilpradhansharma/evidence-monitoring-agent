"""Unit tests for the Claude orchestrator + scorer client (offline/mock mode).

Covers: model id sourced from config (never hard-coded), deterministic offline mock for both
roles, the role logged on every call (ORCHESTRATOR vs TARGET), the structured-score contract,
and the boundary that the client never decides alerts or alters rankings (Principle VIII).
"""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from evidence_monitor.config.settings import Settings
from evidence_monitor.data_access.models import CitationStatus, CompetitivePosition
from evidence_monitor.llm.client import (
    ClaudeClient,
    ClaudeCompletion,
    ClaudeRole,
    ScoreResult,
    ScoringOutput,
)

_MODEL = "config-model-1"  # generic placeholder; the real id only ever comes from config


def _client(**kwargs) -> ClaudeClient:
    return ClaudeClient(model_id=_MODEL, mock=True, **kwargs)


class _RecordingHandler(logging.Handler):
    """Capture emitted records so we can assert on the role/context fields."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _logger_with_capture() -> tuple[logging.Logger, _RecordingHandler]:
    logger = logging.getLogger("test.llm.client")
    logger.handlers.clear()
    handler = _RecordingHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger, handler


# --- construction / config -------------------------------------------------- #
def test_model_id_required_and_not_hard_coded():
    with pytest.raises(ValueError):
        ClaudeClient(model_id="", mock=True)


def test_from_settings_sources_model_id_and_mock_flag():
    settings = Settings(CLAUDE_MODEL_ID="from-config-x", EM_OFFLINE_MOCK=True)
    client = ClaudeClient.from_settings(settings)
    result = client.orchestrate("coordinate dispatch")
    assert result.model_version == "from-config-x"  # id flows from config, never a literal


# --- orchestrator role ------------------------------------------------------ #
def test_mock_orchestrate_is_deterministic_and_uses_config_model():
    client = _client()
    a = client.orchestrate("do the thing")
    b = client.orchestrate("do the thing")
    assert isinstance(a, ClaudeCompletion)
    assert a == b  # identical inputs -> identical outputs
    assert a.model_version == _MODEL
    assert a.text and a.input_tokens > 0 and a.output_tokens > 0


# --- scorer role ------------------------------------------------------------ #
def test_mock_score_returns_valid_structured_output():
    result = _client().score(response_text="some answer", system_prompt="score this generically")
    assert isinstance(result, ScoreResult)
    out = result.output
    assert isinstance(out, ScoringOutput)
    assert -1.0 <= out.sentiment_score <= 1.0
    assert isinstance(out.competitive_position, CompetitivePosition)
    assert isinstance(out.citation_status, CitationStatus)
    assert out.scoring_rationale  # explainability field present (Principle VII)
    assert result.model_version == _MODEL


def test_mock_score_is_deterministic():
    client = _client()
    first = client.score(response_text="x", system_prompt="p")
    second = client.score(response_text="x", system_prompt="p")
    assert first == second


# --- role logged on every call --------------------------------------------- #
def test_role_logged_on_every_call():
    logger, handler = _logger_with_capture()
    client = _client(logger=logger)
    client.orchestrate("c")
    client.score(response_text="r", system_prompt="p")

    contexts = [getattr(r, "context", {}) for r in handler.records]
    assert len(contexts) == 2
    assert all(c.get("role") == "ORCHESTRATOR" for c in contexts)
    assert {c.get("operation") for c in contexts} == {"orchestrate", "score"}
    assert all(c.get("model") == _MODEL for c in contexts)


def test_role_value_is_orchestrator_distinct_from_target():
    # The client is the orchestrator/scorer; the monitored Claude target is a separate adapter.
    assert _client().role is ClaudeRole.ORCHESTRATOR
    assert ClaudeRole.TARGET != ClaudeRole.ORCHESTRATOR
    target_client = _client(role=ClaudeRole.TARGET)
    logger, handler = _logger_with_capture()
    target_client._logger = logger
    target_client.orchestrate("c")
    assert handler.records[0].context["role"] == "TARGET"


# --- boundary: scores, does not decide --------------------------------------- #
def test_scoring_output_has_no_alert_or_ranking_fields():
    # Principle VIII: the model produces a score; code decides alerts. No alert/severity field.
    fields = set(ScoringOutput.model_fields)
    assert not (fields & {"alert", "alert_rule", "severity", "rank", "ranking"})


def test_client_module_does_not_import_alert_logic():
    import evidence_monitor.llm.client as client_module

    assert not hasattr(client_module, "AlertRule")
    assert not hasattr(client_module, "Alert")


def test_scoring_output_enforces_schema_bounds():
    with pytest.raises(ValidationError):
        ScoringOutput(
            sentiment_score=2.0,  # out of [-1, 1]
            competitive_position=CompetitivePosition.NOT_MENTIONED,
            citation_status=CitationStatus.ABSENT,
            scoring_rationale="r",
        )
    with pytest.raises(ValidationError):
        ScoringOutput(
            sentiment_score=0.0,
            competitive_position=CompetitivePosition.NOT_MENTIONED,
            citation_status=CitationStatus.ABSENT,
            key_claims=["1", "2", "3", "4", "5", "6"],  # > 5
            scoring_rationale="r",
        )


def test_mock_needs_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Must not raise / must not touch the network.
    assert _client().score(response_text="x", system_prompt="p").output.scoring_rationale
