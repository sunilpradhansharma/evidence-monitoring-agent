"""Scoring pass: turn a captured :class:`Response` into a versioned :class:`ScoringRecord`.

A thin domain service over the Claude scorer client (``llm/client.py``). It maps the structured
:class:`ScoringOutput` Claude returns onto a :class:`ScoringRecord` linked by ``response_id`` —
it never mutates the response (Principle II), and it makes no alert decision (Principle VIII).
Every record carries the explainability fields the constitution requires: ``brand_mentions``,
``key_claims`` (≤5), and a ``scoring_rationale`` (Principle VII).

The model id comes from config via the injected :class:`ClaudeClient` (Principle V). The MA-reviewed
scoring prompt is a separate concern (``scoring/prompts.py``, US2); a generic, content-agnostic
default is used until that lands.
"""

from __future__ import annotations

from dataclasses import dataclass

from evidence_monitor.data_access.models import ScoringRecord
from evidence_monitor.llm.client import ClaudeClient
from evidence_monitor.response_repo.schema import Response

# Content-agnostic placeholder instruction (no brand/drug/indication names). The MA-reviewed
# prompt replaces this in scoring/prompts.py.
_DEFAULT_SYSTEM_PROMPT = (
    "You assess one public LLM response about a therapy versus its competitors. Return a "
    "structured score: sentiment toward our therapy on a -1..+1 scale, the competitive position, "
    "the citation status, the brands you detected, up to five key claims, and a short rationale."
)


@dataclass(frozen=True)
class Scored:
    """A produced scoring record plus the token cost of the scoring call (for run totals)."""

    record: ScoringRecord
    tokens: int


class Scorer:
    """Produce a :class:`ScoringRecord` for a response via the Claude scorer client."""

    def __init__(self, client: ClaudeClient, *, system_prompt: str | None = None) -> None:
        self._client = client
        self._system_prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT

    def score(self, response: Response) -> Scored:
        """Score one response. Returns the unversioned record; the store assigns the version."""
        result = self._client.score(
            response_text=response.response_text, system_prompt=self._system_prompt
        )
        out = result.output
        record = ScoringRecord(
            response_id=response.response_id,
            sentiment_score=out.sentiment_score,
            competitive_position=out.competitive_position,
            citation_status=out.citation_status,
            brand_mentions=out.brand_mentions,
            key_claims=out.key_claims,
            scoring_rationale=out.scoring_rationale,
            scorer_model=result.model_version,
        )
        return Scored(record=record, tokens=result.input_tokens + result.output_tokens)


__all__ = ["Scored", "Scorer"]
