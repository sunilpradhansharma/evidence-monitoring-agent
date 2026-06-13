"""Unit tests for the base adapter engine: retry/backoff, status mapping, rate limit, mock mode.

Every branch runs through deterministic OFFLINE/MOCK mode — no network, no API keys (Principle
XI). ``sleep`` is injected so backoff/rate-limit timing is asserted without real delay.
"""

from __future__ import annotations

from evidence_monitor.data_access.models import FinishReason, LLMTarget, Persona, ResponseStatus
from evidence_monitor.llm.adapters.base import BaseAdapter, LLMAdapter, MockBehavior


def _target(**over: object) -> LLMTarget:
    fields: dict[str, object] = {
        "target_id": "t",
        "llm_name": "t",
        "model_version": "m-1",
        "rpm_limit": 0,  # disable the rate-limit gate unless a test opts in
    }
    fields.update(over)
    return LLMTarget(**fields)


def _adapter(
    behavior: MockBehavior = MockBehavior.SUCCESS,
    *,
    rpm: int = 0,
    max_attempts: int = 3,
) -> tuple[BaseAdapter, list[float]]:
    slept: list[float] = []
    adapter = BaseAdapter(
        _target(rpm_limit=rpm),
        mock=True,
        mock_behavior=behavior,
        max_attempts=max_attempts,
        sleep=slept.append,
    )
    return adapter, slept


def _submit(adapter: BaseAdapter):
    return adapter.submit(question_text="What is X?", persona=Persona.PROSPECT, system_prompt="sys")


def test_satisfies_adapter_protocol():
    adapter, _ = _adapter()
    assert isinstance(adapter, LLMAdapter)


def test_success_branch():
    adapter, slept = _adapter(MockBehavior.SUCCESS)
    r = _submit(adapter)
    assert r.status is ResponseStatus.SUCCESS
    assert r.finish_reason is FinishReason.STOP
    assert r.attempts == 1
    assert r.response_text and r.block_reason is None
    assert slept == []  # no retries, no backoff


def test_empty_success_is_success_with_empty_text():
    adapter, _ = _adapter(MockBehavior.EMPTY)
    r = _submit(adapter)
    assert r.status is ResponseStatus.SUCCESS
    assert r.response_text == ""
    assert r.finish_reason is FinishReason.STOP


def test_truncated_does_bump_and_retry():
    adapter, _ = _adapter(MockBehavior.TRUNCATED)
    r = _submit(adapter)
    assert r.status is ResponseStatus.TRUNCATED
    assert r.finish_reason is FinishReason.LENGTH
    assert r.attempts == 2  # original try + one max_tokens bump


def test_safety_block_maps_to_blocked():
    adapter, _ = _adapter(MockBehavior.SAFETY_BLOCK)
    r = _submit(adapter)
    assert r.status is ResponseStatus.BLOCKED
    assert r.finish_reason is FinishReason.SAFETY
    assert r.block_reason  # non-empty, non-secret reason


def test_permanent_error_fails_without_retry():
    adapter, slept = _adapter(MockBehavior.PERMANENT_ERROR)
    r = _submit(adapter)
    assert r.status is ResponseStatus.FAILED
    assert r.finish_reason is FinishReason.ERROR
    assert r.attempts == 1
    assert slept == []  # permanent errors are not retried


def test_transient_then_success_retries_once():
    adapter, slept = _adapter(MockBehavior.TRANSIENT_THEN_SUCCESS)
    r = _submit(adapter)
    assert r.status is ResponseStatus.SUCCESS
    assert r.attempts == 2
    assert slept == [2.0]  # one backoff before the successful retry


def test_retry_budget_exhausted_fails_with_backoff():
    adapter, slept = _adapter(MockBehavior.ALWAYS_TRANSIENT, max_attempts=3)
    r = _submit(adapter)
    assert r.status is ResponseStatus.FAILED
    assert r.finish_reason is FinishReason.ERROR
    assert r.attempts == 3
    assert slept == [2.0, 4.0]  # 3 attempts → 2 backoffs (exponential 2s, 4s)


def test_backoff_schedule_is_exponential_2_4_8():
    adapter, _ = _adapter()
    params = adapter._default_params
    assert [params.backoff_for(n) for n in (1, 2, 3)] == [2.0, 4.0, 8.0]


def test_four_attempts_use_2_4_8_backoff():
    adapter, slept = _adapter(MockBehavior.ALWAYS_TRANSIENT, max_attempts=4)
    _submit(adapter)
    assert slept == [2.0, 4.0, 8.0]  # 4 attempts → 3 backoffs


def test_mock_is_deterministic():
    a1, _ = _adapter()
    a2, _ = _adapter()
    assert _submit(a1) == _submit(a2)  # identical inputs → identical outputs


def test_rate_limit_gate_spaces_calls():
    # rpm=60 → one call/second; the second immediate call must wait ~1s.
    adapter, slept = _adapter(MockBehavior.SUCCESS, rpm=60)
    _submit(adapter)  # first call: no prior, no wait
    _submit(adapter)  # second call: gated
    assert len(slept) == 1
    assert 0.0 < slept[0] <= 1.0


def test_model_version_comes_from_config():
    adapter, _ = _adapter()
    r = _submit(adapter)
    assert r.model_version == "m-1"  # resolved from the target config, never hard-coded
