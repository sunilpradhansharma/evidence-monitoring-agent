"""Append-only audit writer (Principle II — every external LLM call is auditable).

The writer exposes exactly one operation: :meth:`append`. There is deliberately no update or
delete path. Rows are written to the ``audit_log`` table that the SQLite store creates; the
writer shares the store's connection so audit entries land in the same transactional database
as the records they describe.

``detail`` is required to be non-secret by contract; redaction of secret-shaped strings is the
caller's responsibility via :mod:`evidence_monitor.observability.logging`.
"""

from __future__ import annotations

import sqlite3

from evidence_monitor.data_access.models import AuditEvent


class SqliteAuditWriter:
    """Concrete :class:`~evidence_monitor.data_access.interface.AuditWriter` over SQLite."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(self, event: AuditEvent) -> None:
        """Insert one audit event. Append-only: no row is ever updated or removed."""
        self._conn.execute(
            """
            INSERT INTO audit_log
                (audit_id, run_id, event_type, role, target, ts, http_status, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.audit_id,
                event.run_id,
                str(event.event_type),
                event.role,
                event.target,
                event.ts.isoformat(),
                event.http_status,
                event.detail,
            ),
        )
        self._conn.commit()

    def all(self) -> list[AuditEvent]:
        """Read every audit event in insertion order (for tests / compliance review)."""
        rows = self._conn.execute(
            """
            SELECT audit_id, run_id, event_type, role, target, ts, http_status, detail
            FROM audit_log
            ORDER BY rowid ASC
            """
        ).fetchall()
        return [
            AuditEvent(
                audit_id=r[0],
                run_id=r[1],
                event_type=r[2],
                role=r[3],
                target=r[4],
                ts=r[5],
                http_status=r[6],
                detail=r[7],
            )
            for r in rows
        ]


__all__ = ["SqliteAuditWriter"]
