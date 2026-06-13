"""Anthropic Claude queried **as an end-user target** — distinct from the orchestrator role.

This adapter monitors what Claude tells an ordinary user, so it uses an end-user system prompt
and is tagged TARGET. It must NOT be confused with ``llm/client.py``, where Claude acts as the
orchestrator/scorer. Model id and limits come from config; the ``anthropic`` SDK is imported
lazily so OFFLINE/MOCK tests need neither the package nor a key.
"""

from __future__ import annotations

from evidence_monitor.llm.adapters.base import (
    AdapterError,
    BaseAdapter,
    TargetParams,
    TransientAdapterError,
    _Kind,
    _RawCompletion,
    _Request,
)


class ClaudeTargetAdapter(BaseAdapter):
    """Claude as a monitored end-user target (role: TARGET, not orchestrator)."""

    role = "TARGET"

    def _call_live(
        self, req: _Request, params: TargetParams, max_tokens: int, attempt: int
    ) -> _RawCompletion:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - live path only
            raise AdapterError("anthropic SDK is not installed") from exc

        client = anthropic.Anthropic()  # API key from env; never logged
        try:
            resp = client.messages.create(
                model=params.model_version,
                max_tokens=max_tokens,
                temperature=params.temperature,
                system=req.system_prompt,
                messages=[{"role": "user", "content": req.question_text}],
            )
        except (anthropic.APITimeoutError, anthropic.RateLimitError) as exc:  # pragma: no cover
            raise TransientAdapterError(f"anthropic transient: {type(exc).__name__}") from exc
        except anthropic.APIStatusError as exc:  # pragma: no cover - live path only
            status = getattr(exc, "status_code", None)
            if status == 429 or (isinstance(status, int) and status >= 500):
                raise TransientAdapterError(f"anthropic transient: {status}") from exc
            raise AdapterError(f"anthropic error: {status}") from exc
        except Exception as exc:  # pragma: no cover - live path only
            raise AdapterError(f"anthropic error: {type(exc).__name__}") from exc

        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        usage = getattr(resp, "usage", None)
        tokens = getattr(usage, "output_tokens", 0) or 0
        if resp.stop_reason == "max_tokens":
            return _RawCompletion(_Kind.LENGTH, text, tokens)
        return _RawCompletion(_Kind.STOP, text, tokens)


__all__ = ["ClaudeTargetAdapter"]
