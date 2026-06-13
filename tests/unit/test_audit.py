"""Unit tests for the append-only audit writer (Principle II)."""

from __future__ import annotations

from tests.fixtures import sample_audit_events

from evidence_monitor.data_access.audit import SqliteAuditWriter
from evidence_monitor.data_access.models import AuditEventType
from evidence_monitor.data_access.sqlite_store import SqliteStore


def test_append_persists_events_in_order():
    store = SqliteStore(":memory:")
    try:
        for event in sample_audit_events():
            store.audit.append(event)
        events = store.audit.all()
        assert [e.event_type for e in events] == [
            AuditEventType.RUN_STARTED,
            AuditEventType.QUERY_DISPATCHED,
            AuditEventType.RESPONSE_RECEIVED,
        ]
    finally:
        store.close()


def test_audit_writer_exposes_no_mutation_surface():
    # The contract is append-only: no update/delete methods exist (Principle II).
    public = {n for n in dir(SqliteAuditWriter) if not n.startswith("_")}
    assert public == {"append", "all"}
    assert not any(verb in public for verb in {"update", "delete", "remove", "edit"})


def test_each_append_is_additive_never_overwrites():
    store = SqliteStore(":memory:")
    try:
        events = sample_audit_events()
        store.audit.append(events[0])
        assert len(store.audit.all()) == 1
        store.audit.append(events[1])
        store.audit.append(events[2])
        # Three distinct rows, none replaced.
        persisted = store.audit.all()
        assert len(persisted) == 3
        assert len({e.audit_id for e in persisted}) == 3
    finally:
        store.close()
