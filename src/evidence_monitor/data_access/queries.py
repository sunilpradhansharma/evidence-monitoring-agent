"""Filtered/paginated response reads and CSV/JSON export (FR-012, FR-025).

The read side of the data-access seam. It turns a
:class:`~evidence_monitor.data_access.interface.QueryFilters` into SQL across every supported
query dimension (LLM, persona, therapeutic area, brand, domain, date range, sentiment range,
alert status, capture status) and serializes results. Storage-specific SQL lives here; the
serializers operate on :class:`Response` objects, so they are storage-agnostic — every store
(SQLite now, Aurora later) reuses them and a view always matches its export.

Brand / therapeutic-area / domain values are carried as opaque query parameters (Principle IV);
this module enumerates none of them.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3

from evidence_monitor.data_access.interface import Page, QueryFilters
from evidence_monitor.data_access.models import Domain, FinishReason, Persona, ResponseStatus
from evidence_monitor.response_repo.schema import Response

# Join the *latest* scoring version per response — sentiment filters read the current score only.
_LATEST_SCORE_JOIN = """
LEFT JOIN (
    SELECT s.response_id, s.sentiment_score
    FROM scoring_records s
    JOIN (SELECT response_id, MAX(version) AS v FROM scoring_records GROUP BY response_id) m
      ON s.response_id = m.response_id AND s.version = m.v
) ls ON ls.response_id = responses.response_id
"""


def row_to_response(r: sqlite3.Row) -> Response:
    """Build the immutable :class:`Response` from one ``responses`` row."""
    return Response(
        response_id=r["response_id"],
        run_id=r["run_id"],
        question_id=r["question_id"],
        target_id=r["target_id"],
        timestamp_utc=r["timestamp_utc"],
        llm_name=r["llm_name"],
        llm_model_version=r["llm_model_version"],
        persona=Persona(r["persona"]),
        therapeutic_area=r["therapeutic_area"],
        brand_focus=r["brand_focus"],
        domain=Domain(r["domain"]),
        response_text=r["response_text"],
        response_tokens=r["response_tokens"],
        finish_reason=FinishReason(r["finish_reason"]),
        status=ResponseStatus(r["status"]),
        block_reason=r["block_reason"],
        alert_triggered=bool(r["alert_triggered"]),
        created_at=r["created_at"],
    )


def _where(filters: QueryFilters) -> tuple[str, list[object]]:
    """Build the WHERE clause + bound params for the set filters (unset fields don't constrain)."""
    clauses: list[str] = []
    params: list[object] = []

    def add(clause: str, value: object) -> None:
        clauses.append(clause)
        params.append(value)

    if filters.run_id is not None:
        add("responses.run_id = ?", filters.run_id)
    if filters.llm is not None:
        add("responses.llm_name = ?", filters.llm)
    if filters.persona is not None:
        add("responses.persona = ?", str(filters.persona))
    if filters.therapeutic_area is not None:
        add("responses.therapeutic_area = ?", filters.therapeutic_area)
    if filters.brand is not None:
        add("responses.brand_focus = ?", filters.brand)
    if filters.domain is not None:
        add("responses.domain = ?", str(filters.domain))
    if filters.status is not None:
        add("responses.status = ?", str(filters.status))
    if filters.date_from is not None:
        add("responses.timestamp_utc >= ?", filters.date_from.isoformat())
    if filters.date_to is not None:
        add("responses.timestamp_utc <= ?", filters.date_to.isoformat())
    if filters.alert_status is not None:
        add("responses.alert_triggered = ?", int(filters.alert_status))
    if filters.sentiment_min is not None:
        add("ls.sentiment_score >= ?", filters.sentiment_min)
    if filters.sentiment_max is not None:
        add("ls.sentiment_score <= ?", filters.sentiment_max)

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def query_responses(
    conn: sqlite3.Connection,
    filters: QueryFilters,
    *,
    page: int = 1,
    page_size: int | None = 50,
) -> Page[Response]:
    """Return a paginated :class:`Page` of responses matching ``filters`` (FR-012).

    ``page_size=None`` returns every match in a single page (used by exports). Results are
    ordered most-recent-first with ``response_id`` as a deterministic tiebreak.
    """
    where, params = _where(filters)
    base = f"FROM responses{_LATEST_SCORE_JOIN}{where}"
    total = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]

    sql = (
        f"SELECT responses.* {base} "
        "ORDER BY responses.timestamp_utc DESC, responses.response_id ASC"
    )
    page_params = list(params)
    if page_size is not None:
        offset = max(0, (max(1, page) - 1) * page_size)
        sql += " LIMIT ? OFFSET ?"
        page_params += [page_size, offset]

    rows = conn.execute(sql, page_params).fetchall()
    items = [row_to_response(r) for r in rows]
    return Page(
        items=items,
        total=total,
        page=page if page_size is not None else 1,
        page_size=page_size if page_size is not None else total,
    )


# --------------------------------------------------------------------------- #
# Export (storage-agnostic — operates on Response objects)
# --------------------------------------------------------------------------- #
_CSV_FIELDS = list(Response.model_fields)


def to_json(rows: list[Response]) -> str:
    """Serialize responses to a pretty JSON array (datetimes/enums as strings)."""
    return json.dumps([r.model_dump(mode="json") for r in rows], indent=2)


def to_csv(rows: list[Response]) -> str:
    """Serialize responses to CSV with a header row; ``None`` renders as an empty cell."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        d = r.model_dump(mode="json")
        writer.writerow({k: ("" if d.get(k) is None else d[k]) for k in _CSV_FIELDS})
    return buf.getvalue()


__all__ = ["query_responses", "row_to_response", "to_csv", "to_json"]
