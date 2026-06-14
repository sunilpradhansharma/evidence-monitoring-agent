"""Scope Reports to a single run — the constitution-safe alternative to deleting old runs.

Old debugging runs stay in the (immutable, audited) store; the Reports view is simply scoped to a
chosen ``run_id`` (or date). Covers: the read-only ``runs.list()`` ordering, that ``build_report``
narrows to one run, and that the served Reports tab renders the Run dropdown and respects it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tests.fixtures import sample_response

from evidence_monitor.api import create_app
from evidence_monitor.config.settings import Settings
from evidence_monitor.dashboard.render import build_report
from evidence_monitor.data_access.interface import QueryFilters
from evidence_monitor.data_access.models import TriggerType
from evidence_monitor.data_access.sqlite_store import SqliteStore


@pytest.fixture
def seeded():
    """Two runs: a 'dirty' one with 2 responses and a 'clean' one with 1."""
    s = SqliteStore(":memory:")
    dirty = s.runs.create(TriggerType.ADHOC)
    clean = s.runs.create(TriggerType.SCHEDULED)
    base = sample_response()
    s.responses.insert(base.model_copy(update={"response_id": "D-1", "run_id": dirty.run_id}))
    s.responses.insert(base.model_copy(update={"response_id": "D-2", "run_id": dirty.run_id}))
    s.responses.insert(base.model_copy(update={"response_id": "C-1", "run_id": clean.run_id}))
    yield s, dirty.run_id, clean.run_id
    s.close()


def test_runs_list_is_most_recent_first(seeded):
    store, dirty_id, clean_id = seeded
    listed = [r.run_id for r in store.runs.list()]
    assert listed == [clean_id, dirty_id]  # clean created later → first


def test_build_report_unscoped_sees_all_runs(seeded):
    store, _, _ = seeded
    data = build_report(store)
    assert data.total_responses == 3
    assert len(data.runs) == 2  # both runs offered in the dropdown


def test_build_report_scoped_to_one_run(seeded):
    store, _, clean_id = seeded
    data = build_report(store, QueryFilters(run_id=clean_id))
    assert data.total_responses == 1  # only the clean run's responses are in view
    assert data.filters["run_id"] == clean_id


def test_reports_tab_renders_run_dropdown(seeded):
    store, dirty_id, clean_id = seeded
    app = create_app(store=store, settings=Settings(_env_file=None))
    with TestClient(app) as c:
        html = c.get("/", params={"tab": "reports"}).text
    assert "All runs" in html
    assert dirty_id[:8] in html and clean_id[:8] in html


def test_reports_tab_scopes_view_by_run_id(seeded):
    store, _, clean_id = seeded
    app = create_app(store=store, settings=Settings(_env_file=None))
    with TestClient(app) as c:
        html = c.get("/", params={"tab": "reports", "run_id": clean_id}).text
    assert "1 response(s) in view" in html  # narrowed to the clean run only
