"""Response Repository — immutable capture + queryable reads/export (US1; FR-008/012/025).

A thin domain service over the ``data_access`` :class:`ResponseRepository` seam (Principle X):
core code depends on the protocol, never on SQLite. It preserves the store's guarantees and adds
the capture/query/export surface the orchestrator and dashboard use.

- **Immutable, write-once** (Principle II) — :meth:`record` delegates to a write-once insert;
  re-recording the same id is refused, and :class:`Response` itself is frozen. There is
  deliberately **no update method**: a captured response is never edited in place.
- **Derived data is separate** — sentiment, competitive position, and citation status never live
  on a Response. They are written as a separate, versioned
  :class:`~evidence_monitor.data_access.models.ScoringRecord` via the ScoringRepository; this
  service offers no path to set them on the response.
- **Queryable** (FR-012) — :meth:`query` filters across every dimension with pagination.
- **Exportable** (FR-025) — :meth:`export_csv` / :meth:`export_json` serialize the *same*
  filtered set a view shows, so a view and its export always match.

Brand / therapeutic-area / domain values flow through as opaque data (Principle IV).
"""

from __future__ import annotations

from evidence_monitor.data_access import queries
from evidence_monitor.data_access.interface import Page, QueryFilters, ResponseRepository
from evidence_monitor.response_repo.schema import Response


class ResponseService:
    """Capture, read, query, and export operations over a :class:`ResponseRepository`."""

    def __init__(self, repo: ResponseRepository) -> None:
        self._repo = repo

    # --- immutable capture ------------------------------------------------- #
    def record(self, response: Response) -> Response:
        """Capture one response, write-once. Re-recording an existing id raises (Principle II)."""
        return self._repo.insert(response)

    def get(self, response_id: str) -> Response | None:
        """One response by id, or ``None`` if unknown."""
        return self._repo.get(response_id)

    # --- queryable reads (FR-012) ----------------------------------------- #
    def query(
        self,
        filters: QueryFilters | None = None,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> Page[Response]:
        """Filtered, paginated reads across every query dimension."""
        return self._repo.query(filters or QueryFilters(), page=page, page_size=page_size)

    # --- export (FR-025) -------------------------------------------------- #
    def export_csv(self, filters: QueryFilters | None = None) -> str:
        """CSV export of every response matching ``filters`` (matches :meth:`query`)."""
        return queries.to_csv(self._all(filters))

    def export_json(self, filters: QueryFilters | None = None) -> str:
        """JSON export of every response matching ``filters`` (matches :meth:`query`)."""
        return queries.to_json(self._all(filters))

    def _all(self, filters: QueryFilters | None) -> list[Response]:
        """Every matching response, unpaginated, for export."""
        return self._repo.query(filters or QueryFilters(), page_size=None).items


__all__ = ["ResponseService"]
