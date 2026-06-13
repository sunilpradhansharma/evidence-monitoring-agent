"""Unit test for the Claude end-user TARGET adapter (distinct from the orchestrator role)."""

from __future__ import annotations

from evidence_monitor.data_access.models import LLMTarget, Persona, ResponseStatus
from evidence_monitor.llm.adapters.base import LLMAdapter
from evidence_monitor.llm.adapters.claude_target import ClaudeTargetAdapter

_TARGET = LLMTarget(
    target_id="anthropic-claude-target",
    llm_name="anthropic-claude-target",
    model_version="claude-3-5-sonnet-20241022",
    rpm_limit=0,
)


def _adapter() -> ClaudeTargetAdapter:
    return ClaudeTargetAdapter(_TARGET, mock=True)


def test_satisfies_protocol():
    assert isinstance(_adapter(), LLMAdapter)


def test_tagged_as_end_user_target_not_orchestrator():
    # The role distinguishes Claude-as-monitored-target from the orchestrator/scorer client.
    assert ClaudeTargetAdapter.role == "TARGET"
    assert _adapter().target_id == "anthropic-claude-target"


def test_mock_submit_succeeds_with_config_model_version():
    r = _adapter().submit(
        question_text="What is X?", persona=Persona.PATIENT, system_prompt="You are a chatbot."
    )
    assert r.status is ResponseStatus.SUCCESS
    assert r.model_version == "claude-3-5-sonnet-20241022"  # from config
    assert r.response_text
