"""Claude (Anthropic API) used in two distinct roles — **orchestrator** and **scorer**.

This is NOT a monitored target. Claude-as-an-end-user lives in
``adapters/claude_target.py`` and is tagged ``TARGET``; this client is tagged ``ORCHESTRATOR``
(the audit/log role taxonomy is ``ORCHESTRATOR`` | ``TARGET`` — see
:class:`~evidence_monitor.data_access.models.AuditEvent`). One class covers both orchestrator
duties (coordinating dispatch via :meth:`ClaudeClient.orchestrate`) and scoring
(:meth:`ClaudeClient.score`).

Hard boundaries (constitution):
- **Model id from config only** (Principle V) — the id is injected at construction, never a
  literal in this module. :meth:`ClaudeClient.from_settings` sources it from
  ``config/settings.py``.
- **Claude scores; code decides** (Principle VIII) — :meth:`score` returns a *structured score*
  and nothing else. It MUST NOT decide whether an alert fires, change a competitive ranking, or
  take any action; that is deterministic code in ``alerts/`` and ``orchestrator/``. This module
  imports neither.
- **Role logged on every call** (FR-031) — each call emits a structured event carrying the role
  (``ORCHESTRATOR`` vs ``TARGET``), operation, and resolved model id. Secrets are never logged.
- **Deterministic OFFLINE/MOCK mode** (Principle XI) — when ``mock=True`` the client returns
  canned results with NO network call and NO API key; identical inputs → identical outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from logging import Logger

from pydantic import BaseModel, ConfigDict, Field, field_validator

from evidence_monitor.config.settings import Settings, get_settings
from evidence_monitor.data_access.models import CitationStatus, CompetitivePosition
from evidence_monitor.observability.logging import get_logger, log_event

# Per-call output ceiling. Not a model id or regulated content — a transport default, overridable
# per call. Model id, by contrast, comes ONLY from config (Principle V).
_DEFAULT_MAX_TOKENS = 1024


class ClaudeRole(StrEnum):
    """Audit/log role for a Claude call.

    The orchestrator + scorer client is ``ORCHESTRATOR``; Claude queried as a monitored
    end-user is ``TARGET`` (``adapters/claude_target.py``). Keeping both values here documents
    the taxonomy the logs and audit trail use.
    """

    ORCHESTRATOR = "ORCHESTRATOR"
    TARGET = "TARGET"


class ScoringOutput(BaseModel):
    """The structured score Claude returns for one response (contract: scoring-output.schema.json).

    Mirrors the JSON schema exactly — the six explainability-bearing fields and nothing else.
    Notably absent: any alert, severity, or ranking field. The scorer never decides actions
    (Principle VIII); deterministic code consumes this object to do that.
    """

    model_config = ConfigDict(extra="forbid")

    sentiment_score: float = Field(ge=-1.0, le=1.0)
    competitive_position: CompetitivePosition
    citation_status: CitationStatus
    brand_mentions: list[str] = Field(default_factory=list)
    # Sentiment toward each detected competitor brand (brand → −1.0..+1.0). Lets code compare a
    # competitor against our therapy for the COMPETITOR_HIGHER rule. Empty when none detected.
    competitor_sentiments: dict[str, float] = Field(default_factory=dict)
    key_claims: list[str] = Field(default_factory=list)
    scoring_rationale: str = Field(min_length=1)

    @field_validator("key_claims")
    @classmethod
    def _at_most_five_claims(cls, v: list[str]) -> list[str]:
        if len(v) > 5:
            raise ValueError("key_claims may contain at most 5 items")
        return v

    @field_validator("competitor_sentiments")
    @classmethod
    def _competitor_sentiments_in_range(cls, v: dict[str, float]) -> dict[str, float]:
        if any(not -1.0 <= score <= 1.0 for score in v.values()):
            raise ValueError("each competitor sentiment must be within -1.0..1.0")
        return v


@dataclass(frozen=True)
class ClaudeCompletion:
    """Result of an orchestrator-role completion."""

    text: str
    input_tokens: int
    output_tokens: int
    model_version: str


@dataclass(frozen=True)
class ScoreResult:
    """A structured score plus the token usage of the call that produced it.

    ``output`` is the score the rest of the system acts on; the token counts feed cost/run
    accounting (``observability/cost.py``).
    """

    output: ScoringOutput
    input_tokens: int
    output_tokens: int
    model_version: str


class ClaudeClient:
    """Claude orchestrator + scorer. Model id from config; deterministic offline mock mode.

    ``sleep``-free and side-effect-light: in mock mode it never touches the network or reads a
    key, so the whole suite runs offline and reproducibly. The live path lazily imports the
    ``anthropic`` SDK so mock tests need neither the package nor a credential.
    """

    def __init__(
        self,
        *,
        model_id: str,
        mock: bool = False,
        role: ClaudeRole = ClaudeRole.ORCHESTRATOR,
        max_retries: int = 2,
        logger: Logger | None = None,
    ) -> None:
        if not model_id:
            raise ValueError("model_id is required and must come from config (Principle V)")
        self._model_id = model_id
        self._mock = mock
        self.role = role
        self._max_retries = max_retries
        self._logger = logger or get_logger("evidence_monitor.llm.client")

    @classmethod
    def from_settings(cls, settings: Settings | None = None, **kwargs) -> ClaudeClient:
        """Build a client with the model id and mock flag sourced from config."""
        s = settings or get_settings()
        return cls(model_id=s.claude_model_id, mock=s.offline_mock, **kwargs)

    # --- orchestrator role ------------------------------------------------ #
    def orchestrate(
        self, instruction: str, *, system: str | None = None, max_tokens: int | None = None
    ) -> ClaudeCompletion:
        """Run one orchestrator-role completion (coordination, not alerting/ranking)."""
        self._log_call("orchestrate")
        max_tokens = max_tokens or _DEFAULT_MAX_TOKENS
        if self._mock:
            return self._mock_orchestrate(instruction)
        return self._orchestrate_live(instruction, system, max_tokens)  # pragma: no cover

    # --- scorer role ------------------------------------------------------ #
    def score(
        self,
        *,
        response_text: str,
        system_prompt: str,
        user_context: str = "",
        max_tokens: int | None = None,
    ) -> ScoreResult:
        """Return a structured :class:`ScoringOutput` for ``response_text``.

        ``system_prompt`` is the MA-reviewed scoring prompt (built in ``scoring/prompts.py``);
        this client owns transport + structured output only, not the prompt content. The result
        is a score and token counts — never an alert decision or a re-ranking.
        """
        self._log_call("score")
        max_tokens = max_tokens or _DEFAULT_MAX_TOKENS
        if self._mock:
            return self._mock_score()
        return self._score_live(  # pragma: no cover
            response_text, system_prompt, user_context, max_tokens
        )

    # --- logging ---------------------------------------------------------- #
    def _log_call(self, operation: str) -> None:
        """Emit the per-call event carrying the role (ORCHESTRATOR vs TARGET) and model id.

        Only non-secret metadata is logged — never the prompt, response, or a credential.
        """
        log_event(
            self._logger,
            "INFO",
            "claude_call",
            role=str(self.role),
            operation=operation,
            model=self._model_id,
            mock=self._mock,
        )

    # --- deterministic OFFLINE/MOCK --------------------------------------- #
    def _mock_orchestrate(self, instruction: str) -> ClaudeCompletion:
        text = f"[mock-orchestrator] {instruction}"
        return ClaudeCompletion(
            text=text,
            input_tokens=max(1, len(instruction.split())),
            output_tokens=max(1, len(text.split())),
            model_version=self._model_id,
        )

    def _mock_score(self) -> ScoreResult:
        """A neutral, deterministic score — every field present so the contract is exercised.

        Deliberately content-agnostic (no brand/drug/indication strings) and constant, so the
        offline suite is reproducible.
        """
        output = ScoringOutput(
            sentiment_score=0.0,
            competitive_position=CompetitivePosition.NOT_MENTIONED,
            citation_status=CitationStatus.ABSENT,
            brand_mentions=[],
            competitor_sentiments={},
            key_claims=["[mock] generic claim"],
            scoring_rationale="[mock] deterministic score (offline mode)",
        )
        return ScoreResult(
            output=output, input_tokens=1, output_tokens=1, model_version=self._model_id
        )

    # --- live calls (lazy SDK import; not exercised by the offline suite) -- #
    def _client(self):  # pragma: no cover - live path only
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("anthropic SDK is not installed") from exc
        # API key resolved from the environment by the SDK; never read or logged here.
        return anthropic.Anthropic().with_options(max_retries=self._max_retries)

    def _orchestrate_live(
        self, instruction: str, system: str | None, max_tokens: int
    ) -> ClaudeCompletion:  # pragma: no cover - live path only
        resp = self._client().messages.create(
            model=self._model_id,
            max_tokens=max_tokens,
            system=system or "",
            messages=[{"role": "user", "content": instruction}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        usage = getattr(resp, "usage", None)
        return ClaudeCompletion(
            text=text,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            model_version=self._model_id,
        )

    def _score_live(
        self, response_text: str, system_prompt: str, user_context: str, max_tokens: int
    ) -> ScoreResult:  # pragma: no cover - live path only
        content = f"{user_context}\n\n{response_text}".strip()
        resp = self._client().messages.parse(
            model=self._model_id,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
            output_format=ScoringOutput,
        )
        usage = getattr(resp, "usage", None)
        return ScoreResult(
            output=resp.parsed_output,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            model_version=self._model_id,
        )


__all__ = [
    "ClaudeClient",
    "ClaudeCompletion",
    "ClaudeRole",
    "ScoreResult",
    "ScoringOutput",
]
