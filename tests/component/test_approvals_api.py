"""Component tests for the local Approvals API (US3, T063).

Drives the FastAPI Approvals endpoints over an injected in-memory store seeded from the real
question bank: list-by-status, approve (recorded + run-eligible), reject (terminal → 409 on
re-approve), and edit (new version, no hard delete). Confirms the read-only/advisory invariant:
the API exposes no submit-to-LLM route.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evidence_monitor.api import create_app
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.question_repo.importer import import_questions

SEED_CSV = Path(__file__).resolve().parents[2] / "data" / "question_bank.csv"


@pytest.fixture
def client():
    store = SqliteStore(":memory:")
    import_questions(store.questions, SEED_CSV)
    app = create_app(store=store)
    with TestClient(app) as c:
        c.store = store  # expose for direct assertions
        yield c
    store.close()


def _first_id(client: TestClient) -> str:
    return client.get("/approvals/questions", params={"status": "PENDING"}).json()[0]["question_id"]


def test_list_questions_filters_by_status(client):
    resp = client.get("/approvals/questions", params={"status": "PENDING"})
    assert resp.status_code == 200
    body = resp.json()
    assert body  # seed imported as PENDING
    assert all(q["approval_status"] == "PENDING" for q in body)
    # No APPROVED questions exist yet.
    assert client.get("/approvals/questions", params={"status": "APPROVED"}).json() == []


def test_approve_records_approver_and_makes_eligible(client):
    qid = _first_id(client)
    resp = client.post(f"/approvals/questions/{qid}/approve", json={"approver_name": "ma_reviewer"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["approval_status"] == "APPROVED"
    assert body["approver_name"] == "ma_reviewer"
    assert body["version"] == 2  # transition recorded as a new version
    # Now run-eligible at the data layer (APPROVED + active).
    assert any(q.question_id == qid for q in client.store.questions.approved_active())


def test_approve_unknown_question_404(client):
    resp = client.post("/approvals/questions/NOPE/approve", json={"approver_name": "ma_reviewer"})
    assert resp.status_code == 404


def test_blank_approver_is_rejected_422(client):
    qid = _first_id(client)
    resp = client.post(f"/approvals/questions/{qid}/approve", json={"approver_name": "   "})
    assert resp.status_code == 422


def test_reject_is_terminal_409_on_reapprove(client):
    qid = _first_id(client)
    rej = client.post(
        f"/approvals/questions/{qid}/reject",
        json={"approver_name": "ma_reviewer", "reason": "off-label phrasing"},
    )
    assert rej.status_code == 200
    assert rej.json()["approval_status"] == "REJECTED"
    # REJECTED is terminal — re-approving conflicts.
    again = client.post(
        f"/approvals/questions/{qid}/approve", json={"approver_name": "ma_reviewer"}
    )
    assert again.status_code == 409


def test_reject_requires_reason_422(client):
    qid = _first_id(client)
    resp = client.post(f"/approvals/questions/{qid}/reject", json={"approver_name": "ma_reviewer"})
    assert resp.status_code == 422


def test_edit_creates_new_version_without_hard_delete(client):
    qid = _first_id(client)
    resp = client.post(
        f"/approvals/questions/{qid}/edit",
        json={"question_text": "A revised, still-generic question?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 2
    assert body["question_text"] == "A revised, still-generic question?"
    # History retained on disk: two rows for this question_id.
    count = client.store.connection.execute(
        "SELECT COUNT(*) FROM questions WHERE question_id = ?", (qid,)
    ).fetchone()[0]
    assert count == 2


def test_edit_with_no_fields_400(client):
    qid = _first_id(client)
    resp = client.post(f"/approvals/questions/{qid}/edit", json={})
    assert resp.status_code == 400


def test_no_submit_endpoint_exists(client):
    """Advisory invariant (Principle I): the API exposes no route that submits to an LLM."""
    paths = client.app.openapi()["paths"]
    assert not any("submit" in p or "run" in p for p in paths)
    # Every exposed path is under the read-only-ish /approvals namespace for this slice.
    assert all(p.startswith("/approvals") for p in paths)
