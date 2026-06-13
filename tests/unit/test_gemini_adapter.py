"""Unit test for the Gemini adapter in mock mode, incl. the safety-block → BLOCKED path."""

from __future__ import annotations

from evidence_monitor.data_access.models import FinishReason, LLMTarget, Persona, ResponseStatus
from evidence_monitor.llm.adapters.base import LLMAdapter, MockBehavior
from evidence_monitor.llm.adapters.gemini import GeminiAdapter

_TARGET = LLMTarget(
    target_id="google-gemini",
    llm_name="google-gemini",
    model_version="gemini-1.5-pro-002",
    rpm_limit=0,
)


def _adapter(behavior: MockBehavior = MockBehavior.SUCCESS) -> GeminiAdapter:
    return GeminiAdapter(_TARGET, mock=True, mock_behavior=behavior)


def _submit(adapter: GeminiAdapter):
    return adapter.submit(question_text="What is X?", persona=Persona.PROVIDER, system_prompt="sys")


def test_satisfies_protocol():
    assert isinstance(_adapter(), LLMAdapter)


def test_mock_submit_succeeds():
    r = _submit(_adapter(MockBehavior.SUCCESS))
    assert r.status is ResponseStatus.SUCCESS
    assert r.model_version == "gemini-1.5-pro-002"


def test_safety_block_maps_to_blocked_not_failed():
    r = _submit(_adapter(MockBehavior.SAFETY_BLOCK))
    assert r.status is ResponseStatus.BLOCKED  # distinct from FAILED
    assert r.finish_reason is FinishReason.SAFETY
    assert r.block_reason  # a non-secret block reason is captured
