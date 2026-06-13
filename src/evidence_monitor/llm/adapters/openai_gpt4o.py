"""OpenAI GPT-4o monitored-target adapter (Chat Completions).

Translates one request into a system+user messages array and maps the finish reason. The model
id, temperature, and limits come from config (Principle V). The ``openai`` SDK is imported lazily
inside :meth:`_call_live` so OFFLINE/MOCK tests need neither the package nor an API key.
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


class OpenAIGpt4oAdapter(BaseAdapter):
    """OpenAI GPT-4o queried as an end-user (Chat Completions)."""

    def _call_live(
        self, req: _Request, params: TargetParams, max_tokens: int, attempt: int
    ) -> _RawCompletion:
        try:
            from openai import (
                APIConnectionError,
                APITimeoutError,
                InternalServerError,
                OpenAI,
                RateLimitError,
            )
        except ImportError as exc:  # pragma: no cover - live path only
            raise AdapterError("openai SDK is not installed") from exc

        client = OpenAI()  # API key sourced from env by the SDK; never logged here
        try:
            resp = client.chat.completions.create(
                model=params.model_version,
                temperature=params.temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": req.system_prompt},
                    {"role": "user", "content": req.question_text},
                ],
            )
        except (
            APITimeoutError,
            APIConnectionError,
            RateLimitError,
            InternalServerError,
        ) as exc:  # pragma: no cover - live path only
            raise TransientAdapterError(f"openai transient: {type(exc).__name__}") from exc
        except Exception as exc:  # pragma: no cover - live path only
            raise AdapterError(f"openai error: {type(exc).__name__}") from exc

        choice = resp.choices[0]
        text = choice.message.content or ""
        tokens = resp.usage.completion_tokens if resp.usage else 0
        if choice.finish_reason == "length":
            return _RawCompletion(_Kind.LENGTH, text, tokens)
        if choice.finish_reason == "content_filter":
            return _RawCompletion(_Kind.SAFETY, text, tokens, block_reason="content_filter")
        return _RawCompletion(_Kind.STOP, text, tokens)


__all__ = ["OpenAIGpt4oAdapter"]
