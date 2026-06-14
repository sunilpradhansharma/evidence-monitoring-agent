"""Unit tests for scoring: JSON-schema parsing and the scorer's record mapping (US2).

Parses the structured object Claude must return (validated against the scoring-output contract),
and checks the scorer maps it to a versioned ScoringRecord linked by response_id without ever
mutating the response (Principle II).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from tests.fixtures import sample_response

from evidence_monitor.data_access.models import CitationStatus, CompetitivePosition
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.llm.client import ClaudeClient, ScoringOutput
from evidence_monitor.scoring.scorer import Scorer

# repo-root/specs/.../contracts/scoring-output.schema.json
SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs/001-evidence-monitoring-poc/contracts/scoring-output.schema.json"
)

_VALID = {
    "sentiment_score": 0.6,
    "competitive_position": "AMONG_OPTIONS",
    "citation_status": "CITED",
    "brand_mentions": ["Brand-X", "rival"],
    "competitor_sentiments": {"rival": 0.8},
    "key_claims": ["claim one", "claim two"],
    "scoring_rationale": "balanced; competitor framed more positively",
}


# --------------------------------------------------------------------------- #
# JSON-schema parsing
# --------------------------------------------------------------------------- #
def test_parses_a_valid_structured_score_from_json():
    out = ScoringOutput.model_validate_json(json.dumps(_VALID))
    assert out.sentiment_score == 0.6
    assert out.competitive_position is CompetitivePosition.AMONG_OPTIONS
    assert out.citation_status is CitationStatus.CITED
    assert out.brand_mentions == ["Brand-X", "rival"]
    assert out.competitor_sentiments == {"rival": 0.8}
    assert len(out.key_claims) == 2


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(sentiment_score=1.5),  # out of -1..+1
        lambda d: d.update(sentiment_score=-2.0),
        lambda d: d.update(key_claims=[f"c{i}" for i in range(6)]),  # > 5
        lambda d: d.update(competitive_position="BOGUS"),  # not in enum
        lambda d: d.update(citation_status="MAYBE"),  # not in enum
        lambda d: d.update(competitor_sentiments={"rival": 2.0}),  # out of range
        lambda d: d.pop("scoring_rationale"),  # required field missing
        lambda d: d.update(unexpected="x"),  # extra field (additionalProperties: false)
    ],
)
def test_rejects_invalid_structured_scores(mutate):
    bad = json.loads(json.dumps(_VALID))
    mutate(bad)
    with pytest.raises(ValidationError):
        ScoringOutput.model_validate(bad)


def test_output_model_matches_the_contract_schema():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for field in schema["required"]:
        assert field in ScoringOutput.model_fields, field
    # Enum domains in the contract match the model's enums.
    assert set(schema["properties"]["citation_status"]["enum"]) == {c.value for c in CitationStatus}
    assert set(schema["properties"]["competitive_position"]["enum"]) == {
        c.value for c in CompetitivePosition
    }


# --------------------------------------------------------------------------- #
# Scorer mapping + versioned persistence (never mutates the response)
# --------------------------------------------------------------------------- #
def test_scorer_stores_versioned_record_linked_to_response_without_mutation():
    store = SqliteStore(":memory:")
    try:
        response = store.responses.insert(sample_response())
        scorer = Scorer(ClaudeClient(model_id="scorer-model-1", mock=True))

        record = scorer.score_and_store(response, store.scores)
        assert record.response_id == response.response_id
        assert record.version == 1
        assert record.scorer_model == "scorer-model-1"
        assert record.scoring_rationale  # explainability present (Principle VII)

        # Re-scoring appends a NEW version; prior version retained; response unchanged.
        again = scorer.score_and_store(response, store.scores)
        assert again.version == 2
        assert len(store.scores.versions_for(response.response_id)) == 2
        assert store.responses.get(response.response_id) == response
    finally:
        store.close()
