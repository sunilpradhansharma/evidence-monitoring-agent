"""Unit tests for the immutable Response schema (Principle II)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from tests.fixtures import sample_response

from evidence_monitor.response_repo.schema import Response, ResponseStatus


def test_response_is_frozen_and_rejects_mutation():
    r = sample_response()
    with pytest.raises(ValidationError):
        r.response_text = "tampered"  # frozen model — no in-place mutation
    with pytest.raises(ValidationError):
        r.status = ResponseStatus.FAILED


def test_response_round_trips_full_text_unedited():
    text = "  Full, unedited answer with   spacing preserved.  "
    r = sample_response().model_copy(update={"response_text": text})
    assert r.response_text == text


def test_response_blocked_carries_reason():
    r = sample_response().model_copy(
        update={"status": ResponseStatus.BLOCKED, "block_reason": "safety_filter"}
    )
    assert r.status is ResponseStatus.BLOCKED
    assert r.block_reason == "safety_filter"


def test_response_rejects_unknown_field():
    # extra="forbid" blocks a stray PII-shaped field at construction (Principle III).
    base = sample_response().model_dump()
    base["ssn"] = "000-00-0000"
    with pytest.raises(ValidationError):
        Response(**base)
