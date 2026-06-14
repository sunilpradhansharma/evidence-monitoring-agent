"""The health probe is HONEST: a real round-trip, not an optimistic string.

``BaseAdapter.health()`` (live mode) runs a minimal real completion through the SAME ``_call_live``
path ``submit()`` uses, so it reports ``reachable`` ONLY when the provider actually answers (key
present + valid, model id accepted, endpoint live), and reports a NON-SECRET classified error
otherwise. Mock mode short-circuits with no network call.
"""

from __future__ import annotations

from evidence_monitor.data_access.models import LLMTarget
from evidence_monitor.llm.adapters.base import (
    AdapterError,
    BaseAdapter,
    _Kind,
    _RawCompletion,
)


def _target(active: bool = True) -> LLMTarget:
    # rpm_limit=0 disables the rate-limit sleep so the probe is instant.
    return LLMTarget(
        target_id="probe", llm_name="probe", model_version="m-1", rpm_limit=0, active=active
    )


class _OKAdapter(BaseAdapter):
    def _call_live(self, req, params, max_tokens, attempt):
        self.calls = getattr(self, "calls", 0) + 1
        return _RawCompletion(_Kind.STOP, "ok", tokens=1)


class _DownAdapter(BaseAdapter):
    def _call_live(self, req, params, max_tokens, attempt):
        raise AdapterError("service unavailable") from ConnectionError("refused")


def test_live_health_passes_only_on_a_real_round_trip():
    a = _OKAdapter(_target(), mock=False)
    result = a.health()
    assert result.reachable is True and result.skipped is False
    assert a.calls == 1  # it actually called the provider
    assert "real round-trip OK" in result.detail


def test_live_health_reports_unreachable_with_classified_nonsecret_error():
    result = _DownAdapter(_target(), mock=False).health()
    assert result.reachable is False and result.skipped is False
    # Classified by the originating cause; non-secret detail only.
    assert "UNREACHABLE" in result.detail and "ConnectionError" in result.detail


def test_mock_health_does_not_touch_the_network():
    a = _OKAdapter(_target(), mock=True)
    result = a.health()
    assert result.reachable is True
    assert not hasattr(a, "calls")  # _call_live never invoked in mock mode
    assert "mock mode" in result.detail
