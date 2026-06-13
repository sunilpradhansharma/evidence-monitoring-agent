"""Unit test for the OpenAI GPT-4o adapter in deterministic OFFLINE/MOCK mode (no key/network)."""

from __future__ import annotations

from evidence_monitor.data_access.models import LLMTarget, Persona, ResponseStatus
from evidence_monitor.llm.adapters.base import LLMAdapter
from evidence_monitor.llm.adapters.openai_gpt4o import OpenAIGpt4oAdapter

_TARGET = LLMTarget(
    target_id="openai-gpt4o",
    llm_name="openai-gpt4o",
    model_version="gpt-4o-2024-08-06",
    rpm_limit=0,
)


def _adapter() -> OpenAIGpt4oAdapter:
    return OpenAIGpt4oAdapter(_TARGET, mock=True)


def test_satisfies_protocol():
    assert isinstance(_adapter(), LLMAdapter)


def test_mock_submit_succeeds_with_config_model_version():
    r = _adapter().submit(question_text="What is X?", persona=Persona.PROSPECT, system_prompt="sys")
    assert r.status is ResponseStatus.SUCCESS
    assert r.model_version == "gpt-4o-2024-08-06"  # from config, never hard-coded
    assert r.response_text
    assert r.attempts == 1


def test_mock_is_deterministic():
    q = {"question_text": "What is X?", "persona": Persona.PATIENT, "system_prompt": "sys"}
    assert _adapter().submit(**q) == _adapter().submit(**q)
