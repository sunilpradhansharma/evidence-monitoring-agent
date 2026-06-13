"""The LLM adapter seam (Principles V & X).

Every monitored target implements one adapter. Adding a target is a new adapter class plus a
``config/targets.yaml`` entry — orchestration never changes. :class:`BaseAdapter` owns all the
cross-cutting behaviour so concrete adapters only translate one provider's request/response:

- **Retry + exponential backoff** — transient failures (timeout / 429 / 5xx, surfaced as
  :class:`TransientAdapterError`) are retried up to ``max_attempts`` (default 3) with backoff
  ``2s / 4s / 8s``. After the budget is exhausted the call returns ``FAILED`` — no exception
  escapes ``submit`` (Principle IX).
- **Per-target rate limiting** — ``rpm_limit`` from config is honoured by a minimum-interval gate.
- **Status mapping** — ``STOP → SUCCESS`` (empty text allowed), ``LENGTH → TRUNCATED`` after a
  bounded ``max_tokens`` bump-and-retry, provider safety filter ``→ BLOCKED`` (distinct from
  FAILED, esp. Gemini).
- **Deterministic OFFLINE/MOCK mode** — returns canned results with NO network call and NO API
  key, so the whole suite is offline and reproducible (Principle XI). Identical inputs →
  identical outputs.

Model ids, params, and rate limits come ONLY from the :class:`LLMTarget` config (Principle V) —
nothing here is hard-coded. Secrets never appear in results or messages (non-secret text only).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from evidence_monitor.data_access.models import (
    FinishReason,
    LLMTarget,
    Persona,
    ResponseStatus,
)

# Default retry/backoff budget (FR-010). Backoff for attempt *n* is ``base * 2**(n-1)`` → 2/4/8s.
_DEFAULT_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 2.0
# One length bump-and-retry: on a truncated reply, double max_tokens once before giving up.
_DEFAULT_MAX_LENGTH_BUMPS = 1
_MAX_TOKEN_CAP = 8192


class TransientAdapterError(Exception):
    """A retryable provider failure (timeout, 429, 5xx). Carries only non-secret text."""


class AdapterError(Exception):
    """A permanent provider/config failure — not retried; mapped to FAILED."""


class _Kind(StrEnum):
    """Normalized completion outcome a concrete adapter reports up to the engine."""

    STOP = "STOP"  # finished normally
    LENGTH = "LENGTH"  # hit the token cap (truncated)
    SAFETY = "SAFETY"  # blocked by a safety/content filter


class MockBehavior(StrEnum):
    """Deterministic OFFLINE behaviours, so every status branch is reachable without a network."""

    SUCCESS = "SUCCESS"
    EMPTY = "EMPTY"  # successful but empty text
    TRUNCATED = "TRUNCATED"  # always length-capped → exercises bump-and-retry → TRUNCATED
    SAFETY_BLOCK = "SAFETY_BLOCK"  # safety filter → BLOCKED
    TRANSIENT_THEN_SUCCESS = "TRANSIENT_THEN_SUCCESS"  # one transient failure, then success
    ALWAYS_TRANSIENT = "ALWAYS_TRANSIENT"  # transient every time → FAILED after budget
    PERMANENT_ERROR = "PERMANENT_ERROR"  # non-retryable error → FAILED immediately


@dataclass(frozen=True)
class TargetParams:
    """Per-call settings resolved from config (Principle V) — never hard-coded."""

    model_version: str
    temperature: float = 0.0
    max_tokens: int = 1024
    rpm_limit: int = 60
    tpm_limit: int = 90_000
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS
    backoff_base: float = _BACKOFF_BASE_SECONDS
    max_length_bumps: int = _DEFAULT_MAX_LENGTH_BUMPS
    max_token_cap: int = _MAX_TOKEN_CAP

    @classmethod
    def from_target(
        cls, target: LLMTarget, *, max_attempts: int = _DEFAULT_MAX_ATTEMPTS
    ) -> TargetParams:
        return cls(
            model_version=target.model_version,
            temperature=target.temperature,
            max_tokens=target.max_tokens,
            rpm_limit=target.rpm_limit,
            tpm_limit=target.tpm_limit,
            max_attempts=max_attempts,
        )

    def backoff_for(self, attempt: int) -> float:
        """Backoff before retrying after a failed ``attempt`` (1-based): 2s, 4s, 8s, …"""
        return self.backoff_base * (2 ** (attempt - 1))


@dataclass(frozen=True)
class _Request:
    question_text: str
    persona: Persona
    system_prompt: str


@dataclass(frozen=True)
class _RawCompletion:
    """What a concrete adapter returns from one provider call (pre status-mapping)."""

    kind: _Kind
    text: str
    tokens: int = 0
    block_reason: str | None = None


@dataclass(frozen=True)
class AdapterResult:
    """The uniform result of :meth:`LLMAdapter.submit` (contract: llm-adapter.md)."""

    status: ResponseStatus
    response_text: str
    response_tokens: int
    finish_reason: FinishReason
    model_version: str
    block_reason: str | None
    attempts: int


@dataclass(frozen=True)
class HealthResult:
    """Reachability + credential signal for preflight (non-secret detail only)."""

    reachable: bool
    detail: str


@runtime_checkable
class LLMAdapter(Protocol):
    """The protocol every monitored target implements. Do not widen or fork it."""

    target_id: str
    name: str

    def submit(
        self,
        *,
        question_text: str,
        persona: Persona,
        system_prompt: str,
        params: TargetParams,
    ) -> AdapterResult: ...

    def health(self) -> HealthResult: ...


class BaseAdapter:
    """Shared engine: retry/backoff, rate limiting, status mapping, and OFFLINE/MOCK mode.

    Concrete adapters implement :meth:`_call_live` (one provider call) and inherit everything
    else. ``sleep`` / ``monotonic`` are injectable so tests assert backoff/rate-limiting with no
    real delay.
    """

    def __init__(
        self,
        target: LLMTarget,
        *,
        mock: bool = False,
        mock_behavior: MockBehavior = MockBehavior.SUCCESS,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.target_id = target.target_id
        self.name = target.llm_name
        self._default_params = TargetParams.from_target(target, max_attempts=max_attempts)
        self._mock = mock
        self._mock_behavior = mock_behavior
        self._sleep = sleep
        self._monotonic = monotonic
        self._min_interval = 60.0 / target.rpm_limit if target.rpm_limit > 0 else 0.0
        self._next_allowed: float | None = None

    # --- public API ------------------------------------------------------- #
    def submit(
        self,
        *,
        question_text: str,
        persona: Persona,
        system_prompt: str,
        params: TargetParams | None = None,
    ) -> AdapterResult:
        """Submit one question, returning a uniform :class:`AdapterResult`. Never raises."""
        params = params or self._default_params
        req = _Request(question_text=question_text, persona=persona, system_prompt=system_prompt)
        try:
            self._rate_limit()
            return self._run(req, params)
        except Exception:  # backstop — no exception ever escapes submit (Principle IX)
            # The exception is intentionally not surfaced verbatim (it may carry provider detail).
            return AdapterResult(
                status=ResponseStatus.FAILED,
                response_text="",
                response_tokens=0,
                finish_reason=FinishReason.ERROR,
                model_version=params.model_version,
                block_reason=None,
                attempts=1,
            )

    def health(self) -> HealthResult:
        if self._mock:
            return HealthResult(reachable=True, detail=f"{self.name}: mock mode (no network)")
        return self._health_live()

    # --- engine ----------------------------------------------------------- #
    def _run(self, req: _Request, params: TargetParams) -> AdapterResult:
        mv = params.model_version
        max_tokens = params.max_tokens
        total_attempts = 0
        last: _RawCompletion | None = None

        for bump in range(params.max_length_bumps + 1):
            raw, used = self._fetch_with_retries(req, max_tokens, params)
            total_attempts += used
            if raw is None:  # transient budget exhausted or permanent error → FAILED
                return AdapterResult(
                    ResponseStatus.FAILED, "", 0, FinishReason.ERROR, mv, None, total_attempts
                )
            if raw.kind is _Kind.SAFETY:
                return AdapterResult(
                    ResponseStatus.BLOCKED,
                    raw.text,
                    raw.tokens,
                    FinishReason.SAFETY,
                    mv,
                    raw.block_reason or "blocked by provider safety filter",
                    total_attempts,
                )
            if raw.kind is _Kind.LENGTH:
                last = raw
                if bump < params.max_length_bumps:
                    max_tokens = min(max_tokens * 2, params.max_token_cap)
                    continue  # bump-and-retry once
                return AdapterResult(
                    ResponseStatus.TRUNCATED,
                    raw.text,
                    raw.tokens,
                    FinishReason.LENGTH,
                    mv,
                    None,
                    total_attempts,
                )
            # _Kind.STOP — success (empty text allowed)
            return AdapterResult(
                ResponseStatus.SUCCESS,
                raw.text,
                raw.tokens,
                FinishReason.STOP,
                mv,
                None,
                total_attempts,
            )

        # Unreachable in practice; preserve the last truncated reply if it happens.
        text = last.text if last else ""
        tokens = last.tokens if last else 0
        return AdapterResult(
            ResponseStatus.TRUNCATED, text, tokens, FinishReason.LENGTH, mv, None, total_attempts
        )

    def _fetch_with_retries(
        self, req: _Request, max_tokens: int, params: TargetParams
    ) -> tuple[_RawCompletion | None, int]:
        """One logical fetch with transient retry + backoff. Returns (completion|None, attempts)."""
        attempts = 0
        for attempt in range(1, params.max_attempts + 1):
            attempts += 1
            try:
                return self._fetch(req, params, max_tokens, attempts), attempts
            except TransientAdapterError:
                if attempt < params.max_attempts:
                    self._sleep(params.backoff_for(attempt))
                    continue
                return None, attempts  # budget exhausted → FAILED
            except AdapterError:
                return None, attempts  # permanent → FAILED, no retry
        return None, attempts

    def _fetch(
        self, req: _Request, params: TargetParams, max_tokens: int, attempt: int
    ) -> _RawCompletion:
        if self._mock:
            return self._mock_fetch(req, max_tokens, attempt)
        return self._call_live(req, params, max_tokens, attempt)

    def _rate_limit(self) -> None:
        """Honor ``rpm_limit`` via a minimum-interval gate (Principle: respect provider limits)."""
        if self._min_interval <= 0:
            return
        now = self._monotonic()
        if self._next_allowed is not None and now < self._next_allowed:
            self._sleep(self._next_allowed - now)
            now = self._next_allowed
        self._next_allowed = now + self._min_interval

    # --- deterministic OFFLINE/MOCK ------------------------------------- #
    def _mock_fetch(self, req: _Request, max_tokens: int, attempt: int) -> _RawCompletion:
        b = self._mock_behavior
        if b is MockBehavior.PERMANENT_ERROR:
            raise AdapterError("mock permanent error")
        if b is MockBehavior.ALWAYS_TRANSIENT:
            raise TransientAdapterError("mock transient error")
        if b is MockBehavior.TRANSIENT_THEN_SUCCESS and attempt < 2:
            raise TransientAdapterError("mock transient error (first attempt)")
        if b is MockBehavior.SAFETY_BLOCK:
            return _RawCompletion(_Kind.SAFETY, "", 0, block_reason="mock safety block")
        if b is MockBehavior.TRUNCATED:
            text = self._mock_text(req)
            return _RawCompletion(_Kind.LENGTH, text, tokens=max_tokens)
        if b is MockBehavior.EMPTY:
            return _RawCompletion(_Kind.STOP, "", tokens=0)
        text = self._mock_text(req)
        return _RawCompletion(_Kind.STOP, text, tokens=max(1, len(text.split())))

    def _mock_text(self, req: _Request) -> str:
        """Deterministic canned text derived from the request (no hard-coded content)."""
        return f"[mock:{self.target_id}] {req.persona} answer to: {req.question_text}"

    # --- live call (concrete adapters implement) ------------------------ #
    def _call_live(
        self, req: _Request, params: TargetParams, max_tokens: int, attempt: int
    ) -> _RawCompletion:
        raise NotImplementedError("concrete adapters implement _call_live")

    def _health_live(self) -> HealthResult:
        return HealthResult(reachable=True, detail=f"{self.name}: live (verified at preflight)")


__all__ = [
    "AdapterError",
    "AdapterResult",
    "BaseAdapter",
    "HealthResult",
    "LLMAdapter",
    "MockBehavior",
    "TargetParams",
    "TransientAdapterError",
]
