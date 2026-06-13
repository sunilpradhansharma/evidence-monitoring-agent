"""Open Evidence — a CONDITIONAL monitored target (Provider-persona only).

Open Evidence is invoked ONLY for PROVIDER-persona questions and ONLY when enabled in config
(``active: true`` with API access confirmed). It is left inactive by default, so its absence
never counts against the capture rate (FR-007). Persona/active gating is decided by the selection
helper in ``registry.py`` (code decides) — this adapter just performs the call.

There is no public SDK; the live path is a generic HTTPS POST to the configured ``endpoint``.
With no endpoint configured the live call is a permanent (non-retryable) failure. OFFLINE/MOCK
mode works with no endpoint and no key.
"""

from __future__ import annotations

from evidence_monitor.data_access.models import LLMTarget
from evidence_monitor.llm.adapters.base import (
    AdapterError,
    BaseAdapter,
    TargetParams,
    TransientAdapterError,
    _Kind,
    _RawCompletion,
    _Request,
)


class OpenEvidenceAdapter(BaseAdapter):
    """Conditional Provider-only target reached over a configured HTTPS endpoint."""

    def __init__(self, target: LLMTarget, **kwargs: object) -> None:
        super().__init__(target, **kwargs)  # type: ignore[arg-type]
        self._endpoint = target.endpoint

    def _call_live(
        self, req: _Request, params: TargetParams, max_tokens: int, attempt: int
    ) -> _RawCompletion:
        if not self._endpoint:
            raise AdapterError("Open Evidence endpoint is not configured")

        import httpx

        try:
            resp = httpx.post(
                self._endpoint,
                json={
                    "model": params.model_version,
                    "system": req.system_prompt,
                    "query": req.question_text,
                    "max_tokens": max_tokens,
                    "temperature": params.temperature,
                },
                timeout=30.0,
            )
        except httpx.TransportError as exc:  # pragma: no cover - live path only
            raise TransientAdapterError("open-evidence transport error") from exc

        if resp.status_code == 429 or resp.status_code >= 500:  # pragma: no cover - live path only
            raise TransientAdapterError(f"open-evidence transient: {resp.status_code}")
        if resp.status_code >= 400:  # pragma: no cover - live path only
            raise AdapterError(f"open-evidence error: {resp.status_code}")

        data = resp.json()  # pragma: no cover - live path only
        text = data.get("answer", "") or ""
        tokens = int(data.get("tokens", 0) or 0)
        if data.get("truncated"):
            return _RawCompletion(_Kind.LENGTH, text, tokens)
        return _RawCompletion(_Kind.STOP, text, tokens)


__all__ = ["OpenEvidenceAdapter"]
