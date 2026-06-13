"""Google Gemini monitored-target adapter.

Sends a system instruction plus the user question and maps Gemini's finish reasons. Gemini's
safety filter is the canonical ``BLOCKED`` case (distinct from FAILED): a ``SAFETY`` finish or a
prompt-feedback block becomes a BLOCKED result carrying a non-secret block reason. Model id and
limits come from config; the ``google-genai`` SDK is imported lazily so mock tests need no key.
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


class GeminiAdapter(BaseAdapter):
    """Google Gemini queried as an end-user; safety blocks map to BLOCKED."""

    def _call_live(
        self, req: _Request, params: TargetParams, max_tokens: int, attempt: int
    ) -> _RawCompletion:
        try:
            from google import genai
            from google.genai import errors, types
        except ImportError as exc:  # pragma: no cover - live path only
            raise AdapterError("google-genai SDK is not installed") from exc

        client = genai.Client()  # API key from env; never logged
        try:
            resp = client.models.generate_content(
                model=params.model_version,
                contents=req.question_text,
                config=types.GenerateContentConfig(
                    system_instruction=req.system_prompt,
                    temperature=params.temperature,
                    max_output_tokens=max_tokens,
                ),
            )
        except errors.APIError as exc:  # pragma: no cover - live path only
            # 429 / 5xx are retryable; other API errors are permanent.
            code = getattr(exc, "code", None)
            if code == 429 or (isinstance(code, int) and code >= 500):
                raise TransientAdapterError(f"gemini transient: {code}") from exc
            raise AdapterError(f"gemini error: {code}") from exc
        except Exception as exc:  # pragma: no cover - live path only
            raise AdapterError(f"gemini error: {type(exc).__name__}") from exc

        # Prompt-level block (no candidates) → BLOCKED.
        feedback = getattr(resp, "prompt_feedback", None)
        if feedback is not None and getattr(feedback, "block_reason", None):
            return _RawCompletion(_Kind.SAFETY, "", 0, block_reason=str(feedback.block_reason))

        candidates = getattr(resp, "candidates", None) or []
        if not candidates:
            return _RawCompletion(_Kind.SAFETY, "", 0, block_reason="no candidates returned")

        candidate = candidates[0]
        finish = str(getattr(candidate, "finish_reason", "") or "")
        text = getattr(resp, "text", "") or ""
        usage = getattr(resp, "usage_metadata", None)
        tokens = getattr(usage, "candidates_token_count", 0) or 0
        if (
            finish.endswith("SAFETY")
            or finish.endswith("BLOCKLIST")
            or finish.endswith("PROHIBITED_CONTENT")
        ):
            return _RawCompletion(_Kind.SAFETY, text, tokens, block_reason=finish)
        if finish.endswith("MAX_TOKENS"):
            return _RawCompletion(_Kind.LENGTH, text, tokens)
        return _RawCompletion(_Kind.STOP, text, tokens)


__all__ = ["GeminiAdapter"]
