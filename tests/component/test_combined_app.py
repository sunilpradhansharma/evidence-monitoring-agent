"""Component tests for the combined local console (US3 + US5).

Asserts the single tabbed app wires Reports (read-only) and Approvals (read-write) together:
an approve/reject action flips status, records the typed approver (SE-002), and appends an
append-only audit entry; the Score-review tab is scaffolded but OFF; ``/health`` runs the
credential preflight.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evidence_monitor.api import create_app
from evidence_monitor.config.settings import Settings
from evidence_monitor.data_access.models import AuditEventType
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.question_repo.importer import import_questions

SEED_CSV = Path(__file__).resolve().parents[2] / "data" / "question_bank.csv"


@pytest.fixture
def store():
    s = SqliteStore(":memory:")
    import_questions(s.questions, SEED_CSV)
    yield s
    s.close()


@pytest.fixture
def client(store):
    app = create_app(store=store)
    with TestClient(app) as c:
        c.store = store
        yield c


def _first_pending_id(client: TestClient) -> str:
    return client.get("/approvals/questions", params={"status": "PENDING"}).json()[0]["question_id"]


# --------------------------------------------------------------------------- #
# Tabs render
# --------------------------------------------------------------------------- #
def test_index_renders_both_tabs(client):
    home = client.get("/html")
    assert home.status_code == 200
    assert "Reports" in home.text and "Approvals" in home.text


def test_approvals_tab_lists_pending_questions(client):
    page = client.get("/html", params={"tab": "approvals"})
    assert page.status_code == 200
    # The pending queue is server-rendered with a reviewer-name field (recorded on every action).
    assert "Pending questions" in page.text
    assert "Reviewer name" in page.text
    assert "data-question-id=" in page.text


# --------------------------------------------------------------------------- #
# Approve / reject write status + approver + an audit entry (the only writes)
# --------------------------------------------------------------------------- #
def test_approve_flips_status_records_approver_and_audits(client):
    qid = _first_pending_id(client)
    before = len(client.store.audit.all())

    resp = client.post(f"/approvals/questions/{qid}/approve", json={"approver_name": "dr_smith"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["approval_status"] == "APPROVED"
    assert body["approver_name"] == "dr_smith"

    events = client.store.audit.all()
    assert len(events) == before + 1
    entry = events[-1]
    assert entry.event_type is AuditEventType.QUESTION_APPROVED
    assert entry.target == qid
    assert "dr_smith" in entry.detail  # approver recorded in the trail


def test_reject_records_reason_and_audits(client):
    qid = _first_pending_id(client)
    resp = client.post(
        f"/approvals/questions/{qid}/reject",
        json={"approver_name": "dr_smith", "reason": "off-label phrasing"},
    )
    assert resp.status_code == 200
    assert resp.json()["approval_status"] == "REJECTED"
    entry = client.store.audit.all()[-1]
    assert entry.event_type is AuditEventType.QUESTION_REJECTED
    assert "off-label phrasing" in entry.detail


def test_edit_creates_version_and_audits(client):
    qid = _first_pending_id(client)
    resp = client.post(
        f"/approvals/questions/{qid}/edit",
        json={"question_text": "A revised, still-generic question?"},
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 2
    entry = client.store.audit.all()[-1]
    assert entry.event_type is AuditEventType.QUESTION_EDITED


# --------------------------------------------------------------------------- #
# Score review removed from the UI; the route stays wired but inert (returns 404)
# --------------------------------------------------------------------------- #
def test_score_review_disabled_returns_404(client):
    # The Score-review tab is removed from the UI, but the route is wired and inert (FR-408).
    assert client.post("/score-review/RESP-1").status_code == 404


def test_score_review_tab_removed_from_ui(client):
    # Two tabs only — the Score-review tab is gone entirely (out of scope).
    page = client.get("/html", params={"tab": "reports"}).text
    assert "Score review" not in page
    assert ">Reports</a>" in page and ">Approvals</a>" in page


# --------------------------------------------------------------------------- #
# Health preflight
# --------------------------------------------------------------------------- #
def test_health_degraded_when_credentials_missing(store):
    app = create_app(store=store, settings=Settings(_env_file=None))
    with TestClient(app) as c:
        resp = c.get("/health")
        assert resp.status_code == 503
        assert resp.json()["status"] == "degraded"
        assert "ANTHROPIC_API_KEY" in resp.json()["missing"]


def test_health_ok_when_credentials_present(store):
    settings = Settings(
        _env_file=None,
        ANTHROPIC_API_KEY="x",
        OPENAI_API_KEY="y",
        GOOGLE_API_KEY="z",
    )
    app = create_app(store=store, settings=settings)
    with TestClient(app) as c:
        resp = c.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
