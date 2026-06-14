"""Component tests for the read-only Approved-questions view on the Approvals tab.

Reads through the question-repository read path (``build_approved_questions`` → ``QuestionService``)
— never SQL from the template. Asserts the view returns EXACTLY the APPROVED + active set (not
PENDING / REJECTED / inactive), carries the required fields, sorts by ``question_id``, and that the
persona / therapeutic-area / domain filters and the free-text search work — plus that the served
Approvals tab renders the section read-only (no approve/reject controls on approved rows).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from evidence_monitor.api import create_app
from evidence_monitor.config.settings import Settings
from evidence_monitor.dashboard.render import build_approved_questions
from evidence_monitor.data_access.models import ApprovalStatus, Domain, Persona, Question
from evidence_monitor.data_access.sqlite_store import SqliteStore


@pytest.fixture
def store():
    s = SqliteStore(":memory:")
    yield s
    s.close()


def _q(qid: str, persona: Persona, ta: str, domain: Domain, text: str) -> Question:
    return Question(
        question_id=qid,
        question_text=text,
        persona=persona,
        therapeutic_area=ta,
        brand_focus="Brand-X",
        domain=domain,
    )


@pytest.fixture
def seeded(store):
    """Three APPROVED+active, one PENDING, one REJECTED, one APPROVED-but-inactive."""
    store.questions.upsert(_q("A-001", Persona.PROSPECT, "Area-One", Domain.EFFICACY, "alpha text"))
    store.questions.upsert(_q("A-002", Persona.PROVIDER, "Area-Two", Domain.SAFETY, "beta text"))
    store.questions.upsert(_q("A-003", Persona.PATIENT, "Area-One", Domain.ACCESS, "gamma text"))
    store.questions.upsert(_q("P-001", Persona.PROSPECT, "Area-One", Domain.EFFICACY, "pending"))
    store.questions.upsert(_q("R-001", Persona.PROVIDER, "Area-Two", Domain.SAFETY, "rejected"))
    store.questions.upsert(_q("I-001", Persona.PATIENT, "Area-One", Domain.ACCESS, "inactive"))

    store.questions.set_approval("A-001", ApprovalStatus.APPROVED, "rev-a", note="ok-a")
    store.questions.set_approval("A-002", ApprovalStatus.APPROVED, "rev-b", note="ok-b")
    store.questions.set_approval("A-003", ApprovalStatus.APPROVED, "rev-c")  # no note
    store.questions.set_approval("R-001", ApprovalStatus.REJECTED, "rev-x", reason="off-label")
    store.questions.set_approval("I-001", ApprovalStatus.APPROVED, "rev-d")
    store.questions.deactivate("I-001", "retired")  # APPROVED but now inactive
    return store


# --------------------------------------------------------------------------- #
# Data: exactly the APPROVED + active set, sorted, with the required fields
# --------------------------------------------------------------------------- #
def test_returns_exactly_the_approved_active_set_sorted(seeded):
    view = build_approved_questions(seeded)
    assert view.total == 3
    assert [q.question_id for q in view.questions] == ["A-001", "A-002", "A-003"]  # sorted
    # PENDING / REJECTED / inactive are excluded.
    ids = {q.question_id for q in view.questions}
    assert ids.isdisjoint({"P-001", "R-001", "I-001"})


def test_rows_carry_the_required_fields(seeded):
    view = build_approved_questions(seeded)
    a1 = next(q for q in view.questions if q.question_id == "A-001")
    assert a1.persona is Persona.PROSPECT
    assert a1.therapeutic_area == "Area-One"
    assert a1.brand_focus == "Brand-X"
    assert a1.domain is Domain.EFFICACY
    assert a1.approval_status is ApprovalStatus.APPROVED
    assert a1.approver_name == "rev-a"
    assert a1.approval_note == "ok-a"
    assert a1.version >= 1
    assert a1.updated_at is not None
    assert a1.question_text == "alpha text"
    # An approval with no note is still shown (note is None).
    a3 = next(q for q in view.questions if q.question_id == "A-003")
    assert a3.approver_name == "rev-c" and a3.approval_note is None


# --------------------------------------------------------------------------- #
# Filters + search
# --------------------------------------------------------------------------- #
def test_persona_filter(seeded):
    view = build_approved_questions(seeded, persona="PROSPECT")
    assert [q.question_id for q in view.questions] == ["A-001"]


def test_therapeutic_area_filter(seeded):
    view = build_approved_questions(seeded, therapeutic_area="Area-Two")
    assert [q.question_id for q in view.questions] == ["A-002"]


def test_domain_filter(seeded):
    view = build_approved_questions(seeded, domain="ACCESS")
    assert [q.question_id for q in view.questions] == ["A-003"]


def test_search_matches_question_id_and_text(seeded):
    assert [q.question_id for q in build_approved_questions(seeded, search="a-002").questions] == [
        "A-002"
    ]
    # matches question_text too (case-insensitive)
    assert [q.question_id for q in build_approved_questions(seeded, search="GAMMA").questions] == [
        "A-003"
    ]


def test_options_list_only_approved_therapeutic_areas(seeded):
    view = build_approved_questions(seeded)
    assert view.options.therapeutic_areas == ["Area-One", "Area-Two"]
    assert "PROSPECT" in view.options.personas and "EFFICACY" in view.options.domains


# --------------------------------------------------------------------------- #
# Served Approvals tab renders the section read-only
# --------------------------------------------------------------------------- #
def test_approvals_tab_renders_approved_section(seeded):
    app = create_app(store=seeded, settings=Settings(_env_file=None))
    with TestClient(app) as c:
        html = c.get("/", params={"tab": "approvals"}).text

    assert "Approved questions (3)" in html
    assert "A-001" in html and "rev-a" in html and "ok-a" in html
    # Read-only: the approved section is a table, not approve/reject forms; excluded rows absent.
    assert "R-001" not in html and "I-001" not in html
    approved_table = html.split("Approved questions (3)", 1)[1]
    assert "onclick=\"act(" not in approved_table  # no write controls on approved rows


def test_approvals_tab_search_narrows_rendered_rows(seeded):
    app = create_app(store=seeded, settings=Settings(_env_file=None))
    with TestClient(app) as c:
        html = c.get("/", params={"tab": "approvals", "search": "beta"}).text
    assert "Approved questions (1)" in html
    assert "A-002" in html and "A-001" not in html.split("Approved questions (1)", 1)[1]
