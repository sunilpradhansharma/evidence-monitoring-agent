"""Scoring pass: turn a captured :class:`Response` into a versioned :class:`ScoringRecord`.

A thin domain service over the Claude scorer client (``llm/client.py``) and the MA-reviewed
prompt (``scoring/prompts.py``). It maps the structured :class:`ScoringOutput` Claude returns onto
a :class:`ScoringRecord` linked by ``response_id`` — it never mutates the response (Principle II),
and it makes no alert decision (Principle VIII). Every record carries the explainability fields the
constitution requires: ``brand_mentions``, ``key_claims`` (≤5), and a ``scoring_rationale``
(Principle VII).

:meth:`Scorer.score_and_store` persists the record through the :class:`ScoringRepository`, which
assigns the next version and links by ``response_id`` (FR-015/018) — re-scoring appends a new
version and never overwrites. The model id comes from config via the injected :class:`ClaudeClient`
(Principle V).
"""

from __future__ import annotations

from dataclasses import dataclass

from evidence_monitor.data_access.interface import ScoringRepository
from evidence_monitor.data_access.models import ScoringRecord
from evidence_monitor.llm.client import ClaudeClient
from evidence_monitor.response_repo.schema import Response
from evidence_monitor.scoring.prompts import SCORING_SYSTEM_PROMPT, build_user_prompt


@dataclass(frozen=True)
class Scored:
    """A produced scoring record plus the token cost of the scoring call (for run totals)."""

    record: ScoringRecord
    tokens: int


class Scorer:
    """Produce (and optionally store) a :class:`ScoringRecord` for a response."""

    def __init__(self, client: ClaudeClient, *, system_prompt: str | None = None) -> None:
        self._client = client
        self._system_prompt = system_prompt or SCORING_SYSTEM_PROMPT

    def score(self, response: Response) -> Scored:
        """Score one response. Returns the unversioned record; the store assigns the version."""
        result = self._client.score(
            response_text=response.response_text,
            system_prompt=self._system_prompt,
            user_context=build_user_prompt(
                brand_focus=response.brand_focus, therapeutic_area=response.therapeutic_area
            ),
        )
        out = result.output
        record = ScoringRecord(
            response_id=response.response_id,
            sentiment_score=out.sentiment_score,
            competitive_position=out.competitive_position,
            citation_status=out.citation_status,
            brand_mentions=out.brand_mentions,
            competitor_sentiments=out.competitor_sentiments,
            key_claims=out.key_claims,
            scoring_rationale=out.scoring_rationale,
            scorer_model=result.model_version,
        )
        return Scored(record=record, tokens=result.input_tokens + result.output_tokens)

    def score_and_store(self, response: Response, scores: ScoringRepository) -> ScoringRecord:
        """Score ``response`` and persist a new, versioned scoring record (response untouched)."""
        return scores.add_version(self.score(response).record)


__all__ = ["Scored", "Scorer"]
