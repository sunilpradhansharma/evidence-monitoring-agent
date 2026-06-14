"""Component tests for the Response Repository (US1; FR-008/012/025).

Proves the two guarantees the task calls out: immutability (write-then-edit fails; no update
path; derived data is not stored on the response) and that filtered/paginated queries — plus
CSV/JSON export — return exactly the matching set.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from tests.fixtures import sample_response, sample_scoring

from evidence_monitor.data_access.interface import QueryFilters
from evidence_monitor.data_access.models import (
    Alert,
    AlertRule,
    Domain,
    Persona,
    ResponseStatus,
)
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.response_repo.repository import ResponseService
from evidence_monitor.response_repo.schema import FinishReason, Response


@pytest.fixture
def store():
    s = SqliteStore(":memory:")
    yield s
    s.close()


@pytest.fixture
def svc(store):
    return ResponseService(store.responses)


def _resp(response_id: str, **overrides) -> Response:
    """Build a generic response; overrides set the dimensions under test (no PII/brands)."""
    base = dict(
        response_id=response_id,
        run_id="RUN-1",
        question_id="Q1",
        target_id="t",
        llm_name="provider-a",
        llm_model_version="m1",
        persona=Persona.PROSPECT,
        therapeutic_area="Area-One",
        brand_focus="Brand-X",
        domain=Domain.EFFICACY,
        response_text=f"answer {response_id}",
        response_tokens=1,
        finish_reason=FinishReason.STOP,
        status=ResponseStatus.SUCCESS,
    )
    base.update(overrides)
    return Response(**base)


def _score(store, response_id: str, sentiment: float) -> None:
    """Attach a scoring version with a chosen sentiment to ``response_id``."""
    record = sample_scoring(response_id=response_id).model_copy(
        update={"sentiment_score": sentiment}
    )
    store.scores.add_version(record)


# --------------------------------------------------------------------------- #
# Immutability
# --------------------------------------------------------------------------- #
def test_record_is_write_once(svc):
    r = sample_response()
    assert svc.record(r) == r
    assert svc.get(r.response_id) == r
    with pytest.raises(ValueError):
        svc.record(r)  # re-recording the same id is refused (Principle II)


def test_stored_response_cannot_be_edited(svc):
    r = sample_response()
    svc.record(r)
    # The frozen model rejects in-place mutation — there is no edit-then-overwrite path.
    with pytest.raises(ValidationError):
        r.response_text = "tampered"
    assert svc.get(r.response_id).response_text == sample_response().response_text


def test_repository_exposes_no_update_path(svc, store):
    # Immutability is structural: neither the service nor the store offers an update/delete.
    for attr in ("update", "edit", "delete", "set", "save"):
        assert not hasattr(svc, attr)
        assert not hasattr(store.responses, attr)


def test_derived_fields_live_only_in_a_separate_versioned_scoring_record(svc, store):
    r = sample_response()
    svc.record(r)
    # Derived scoring data is not a field on Response — it cannot be written there at all.
    assert "sentiment_score" not in Response.model_fields
    assert "competitive_position" not in Response.model_fields

    # It goes into a separate, versioned ScoringRecord; the response is untouched.
    store.scores.add_version(sample_scoring(response_id=r.response_id))
    store.scores.add_version(sample_scoring(response_id=r.response_id))
    assert len(store.scores.versions_for(r.response_id)) == 2
    assert svc.get(r.response_id) == r  # response unchanged by scoring


# --------------------------------------------------------------------------- #
# Filtered queries — one dimension at a time
# --------------------------------------------------------------------------- #
def _ids(page) -> set[str]:
    return {r.response_id for r in page.items}


def test_query_filters_each_dimension(svc, store):
    svc.record(_resp("base"))
    svc.record(_resp("llm-b", llm_name="provider-b"))
    svc.record(_resp("prov", persona=Persona.PROVIDER))
    svc.record(_resp("area2", therapeutic_area="Area-Two"))
    svc.record(_resp("brandY", brand_focus="Brand-Y"))
    svc.record(_resp("safety", domain=Domain.SAFETY))
    svc.record(_resp("failed", status=ResponseStatus.FAILED))
    svc.record(_resp("alerted"))
    # Alert state is derived from an Alert record (responses are immutable), not a stored flag.
    store.alerts.insert(
        Alert.for_rule(
            score_id="s1", response_id="alerted", rule=AlertRule.NEGATIVE_SENTIMENT, reason="neg"
        )
    )

    assert _ids(svc.query(QueryFilters(llm="provider-b"))) == {"llm-b"}
    assert _ids(svc.query(QueryFilters(persona=Persona.PROVIDER))) == {"prov"}
    assert _ids(svc.query(QueryFilters(therapeutic_area="Area-Two"))) == {"area2"}
    assert _ids(svc.query(QueryFilters(brand="Brand-Y"))) == {"brandY"}
    assert _ids(svc.query(QueryFilters(domain="SAFETY"))) == {"safety"}
    assert _ids(svc.query(QueryFilters(status=ResponseStatus.FAILED))) == {"failed"}
    assert _ids(svc.query(QueryFilters(alert_status=True))) == {"alerted"}
    # No filter → everything.
    assert svc.query(QueryFilters()).total == 8


def test_alert_triggered_is_derived_from_alert_records(svc, store):
    # Responses are immutable, so alert_triggered is derived from the alerts table on read.
    svc.record(_resp("r"))
    assert svc.get("r").alert_triggered is False
    assert _ids(svc.query(QueryFilters(alert_status=False))) == {"r"}
    assert _ids(svc.query(QueryFilters(alert_status=True))) == set()

    store.alerts.insert(
        Alert.for_rule(
            score_id="s", response_id="r", rule=AlertRule.WRONG_INDICATION, reason="wrong"
        )
    )
    # Same stored (immutable) row now reads as alert-triggered, via get() and query().
    assert svc.get("r").alert_triggered is True
    assert _ids(svc.query(QueryFilters(alert_status=True))) == {"r"}
    assert _ids(svc.query(QueryFilters(alert_status=False))) == set()


def test_query_filters_by_run_id(svc):
    svc.record(_resp("a", run_id="RUN-A"))
    svc.record(_resp("b", run_id="RUN-B"))
    assert _ids(svc.query(QueryFilters(run_id="RUN-A"))) == {"a"}
    assert _ids(svc.query(QueryFilters(run_id="RUN-B"))) == {"b"}


def test_query_filters_date_range(svc):
    old = datetime(2020, 1, 1, tzinfo=UTC)
    new = datetime(2025, 6, 1, tzinfo=UTC)
    svc.record(_resp("old", timestamp_utc=old))
    svc.record(_resp("new", timestamp_utc=new))

    cutoff = datetime(2024, 1, 1, tzinfo=UTC)
    assert _ids(svc.query(QueryFilters(date_from=cutoff))) == {"new"}
    assert _ids(svc.query(QueryFilters(date_to=cutoff))) == {"old"}


def test_query_filters_sentiment_range_using_latest_score(svc, store):
    svc.record(_resp("pos"))
    svc.record(_resp("neg"))
    svc.record(_resp("unscored"))
    _score(store, "pos", 0.8)
    _score(store, "neg", -0.5)

    assert _ids(svc.query(QueryFilters(sentiment_min=0.5))) == {"pos"}
    assert _ids(svc.query(QueryFilters(sentiment_max=0.0))) == {"neg"}
    # A response with no score is excluded whenever a sentiment bound is set.
    assert "unscored" not in _ids(svc.query(QueryFilters(sentiment_min=-1.0)))


def test_query_sentiment_reads_only_the_latest_version(svc, store):
    svc.record(_resp("r"))
    _score(store, "r", -0.9)
    _score(store, "r", 0.9)
    # Latest is +0.9, so a positive filter matches and a negative one does not.
    assert _ids(svc.query(QueryFilters(sentiment_min=0.5))) == {"r"}
    assert _ids(svc.query(QueryFilters(sentiment_max=0.0))) == set()


def test_query_combines_filters_with_and(svc):
    svc.record(_resp("a", llm_name="provider-b", domain=Domain.SAFETY))
    svc.record(_resp("b", llm_name="provider-b", domain=Domain.EFFICACY))
    page = svc.query(QueryFilters(llm="provider-b", domain="SAFETY"))
    assert _ids(page) == {"a"}


# --------------------------------------------------------------------------- #
# Pagination
# --------------------------------------------------------------------------- #
def test_query_paginates(svc):
    for i in range(5):
        svc.record(_resp(f"r{i}", timestamp_utc=datetime(2025, 1, i + 1, tzinfo=UTC)))
    p1 = svc.query(QueryFilters(), page=1, page_size=2)
    p2 = svc.query(QueryFilters(), page=2, page_size=2)
    p3 = svc.query(QueryFilters(), page=3, page_size=2)

    assert p1.total == p2.total == 5
    assert (len(p1.items), len(p2.items), len(p3.items)) == (2, 2, 1)
    # Pages are disjoint and cover the whole set.
    assert _ids(p1) | _ids(p2) | _ids(p3) == {f"r{i}" for i in range(5)}
    assert _ids(p1) & _ids(p2) == set()
    # Ordered most-recent-first.
    assert [r.response_id for r in p1.items] == ["r4", "r3"]


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def test_export_json_matches_filtered_query(svc):
    svc.record(_resp("keep", llm_name="provider-b"))
    svc.record(_resp("drop", llm_name="provider-a"))
    filters = QueryFilters(llm="provider-b")

    rows = json.loads(svc.export_json(filters))
    assert [row["response_id"] for row in rows] == ["keep"]
    assert rows[0]["llm_name"] == "provider-b"


def test_export_csv_has_header_and_one_row_per_match(svc):
    svc.record(_resp("r1"))
    svc.record(_resp("r2", status=ResponseStatus.BLOCKED, block_reason="safety"))

    text = svc.export_csv(QueryFilters())
    reader = list(csv.DictReader(io.StringIO(text)))
    assert len(reader) == 2
    assert {row["response_id"] for row in reader} == {"r1", "r2"}
    # None renders as an empty cell; populated reasons survive the round-trip.
    by_id = {row["response_id"]: row for row in reader}
    assert by_id["r1"]["block_reason"] == ""
    assert by_id["r2"]["block_reason"] == "safety"


def test_export_covers_all_matches_ignoring_pagination(svc):
    for i in range(120):
        svc.record(_resp(f"r{i}"))
    # Default page_size is 50, but export must include every matching record.
    assert len(json.loads(svc.export_json(QueryFilters()))) == 120
