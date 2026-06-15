"""Component tests for the CLI (US1/US5): run summary, subset filter, budget pause, health/dry-run.

Runs fully offline (mock adapters). The command functions take an injected in-memory store, so no
filesystem or network is touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.fixtures import sample_questions

from evidence_monitor import cli
from evidence_monitor.config.settings import Settings
from evidence_monitor.data_access.interface import QueryFilters
from evidence_monitor.data_access.models import ApprovalStatus, AuditEventType, Domain, Persona
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.orchestrator.state import QuestionFilter, RunSummary
from evidence_monitor.question_repo.approval import ApprovalError
from evidence_monitor.response_repo.repository import ResponseService

TARGETS_CFG = str(Path(__file__).resolve().parents[2] / "src/evidence_monitor/config/targets.yaml")


def _settings(**overrides) -> Settings:
    return Settings(EM_OFFLINE_MOCK=True, EM_TARGETS_CONFIG=TARGETS_CFG, **overrides)


@pytest.fixture
def store():
    s = SqliteStore(":memory:")
    for q in sample_questions():
        s.questions.upsert(q)
        s.questions.set_approval(q.question_id, ApprovalStatus.APPROVED, "reviewer")
    yield s
    s.close()


def _responses(store):
    return ResponseService(store.responses).query(QueryFilters(), page_size=None).items


# --------------------------------------------------------------------------- #
# Run summary
# --------------------------------------------------------------------------- #
def test_run_produces_full_summary(store):
    summary = cli.cmd_run(_settings(), store, mock=True)

    assert isinstance(summary, RunSummary)
    assert summary.questions_attempted == 3
    # 10 = PROSPECT + PATIENT × 3 unconditional targets, plus PROVIDER × 4 (the 3 unconditional
    # targets and the active PROVIDER-only provider-evidence-dev stand-in).
    assert summary.responses_by_status == {"SUCCESS": 10}
    assert summary.responses_captured == 10
    assert summary.alert_count == 0
    assert summary.total_tokens > 0
    assert summary.est_cost > 0  # priced from config (targets.yaml prices)
    assert summary.budget_exhausted is False


# --------------------------------------------------------------------------- #
# Subset filter
# --------------------------------------------------------------------------- #
def test_subset_filter_by_persona(store):
    summary = cli.cmd_run(
        _settings(), store, mock=True, question_filter=QuestionFilter(persona=Persona.PROVIDER)
    )
    assert summary.questions_attempted == 1  # only the PROVIDER question
    personas = {r.persona for r in _responses(store)}
    assert personas == {Persona.PROVIDER}
    # The PROVIDER question reaches 4 active targets: the 3 unconditional providers plus the active
    # PROVIDER-only provider-evidence-dev stand-in.
    assert summary.responses_captured == 4


def test_subset_filter_by_domain(store):
    summary = cli.cmd_run(
        _settings(), store, mock=True, question_filter=QuestionFilter(domain=Domain.SAFETY)
    )
    assert summary.questions_attempted == 1  # only the SAFETY-domain question
    assert {r.domain for r in _responses(store)} == {Domain.SAFETY}


def test_subset_filter_no_match_runs_empty(store):
    summary = cli.cmd_run(
        _settings(),
        store,
        mock=True,
        question_filter=QuestionFilter(persona=Persona.PROVIDER, domain=Domain.ACCESS),
    )
    assert summary.questions_attempted == 0
    assert _responses(store) == []


# --------------------------------------------------------------------------- #
# Budget enforcement (pause rather than overrun)
# --------------------------------------------------------------------------- #
def test_run_pauses_when_token_budget_reached(store):
    summary = cli.cmd_run(_settings(EM_MAX_TOKENS_PER_RUN=1), store, mock=True)
    assert summary.budget_exhausted is True
    # Paused after the first question's targets — not the whole bank of 9.
    assert summary.responses_captured == 3


# --------------------------------------------------------------------------- #
# Connectivity / dry-run
# --------------------------------------------------------------------------- #
def test_health_check_reports_all_targets_reachable():
    assert cli.cmd_health_check(_settings(), mock=True) is True


def test_dry_run_validates_and_writes_nothing(tmp_path):
    db = tmp_path / "evidence.db"
    settings = _settings(EM_DB_PATH=str(db))
    assert cli.cmd_dry_run(settings, mock=True) is True
    # dry-run touches no storage.
    assert not db.exists()


# --------------------------------------------------------------------------- #
# main() argument routing (exit codes)
# --------------------------------------------------------------------------- #
def test_main_routes_each_command(monkeypatch, tmp_path):
    # Point main()'s settings at an isolated DB + the real targets config; force mock.
    monkeypatch.setattr(cli, "get_settings", lambda: _settings(EM_DB_PATH=str(tmp_path / "e.db")))
    assert cli.main(["--mock", "health-check"]) == 0
    assert cli.main(["--mock", "dry-run"]) == 0
    assert cli.main(["--mock", "run"]) == 0
    assert cli.main(["--mock", "subset", "--persona", "PROVIDER", "--domain", "SAFETY"]) == 0


# --------------------------------------------------------------------------- #
# Approve / reject — the scriptable path to the approval workflow (+ audit)
# --------------------------------------------------------------------------- #
@pytest.fixture
def pending_store():
    s = SqliteStore(":memory:")
    for q in sample_questions():
        s.questions.upsert(q)  # imported as PENDING
    yield s
    s.close()


def test_cli_approve_flips_status_and_audits(pending_store):
    question = cli.cmd_approve(pending_store, "Q-PROV-1", "dr_smith")
    assert question.approval_status is ApprovalStatus.APPROVED
    assert question.approver_name == "dr_smith"
    entry = pending_store.audit.all()[-1]
    assert entry.event_type is AuditEventType.QUESTION_APPROVED
    assert entry.target == "Q-PROV-1"


def test_cli_reject_records_reason_and_audits(pending_store):
    cli.cmd_reject(pending_store, "Q-PROV-1", "dr_smith", "off-label phrasing")
    entry = pending_store.audit.all()[-1]
    assert entry.event_type is AuditEventType.QUESTION_REJECTED
    assert "off-label phrasing" in entry.detail


def test_cli_approve_unknown_question_raises(pending_store):
    with pytest.raises(KeyError):
        cli.cmd_approve(pending_store, "NOPE", "dr_smith")


def test_main_routes_approve_and_reject(monkeypatch, tmp_path):
    db = tmp_path / "e.db"
    store = SqliteStore(str(db))
    for q in sample_questions():
        store.questions.upsert(q)
    store.close()
    monkeypatch.setattr(cli, "get_settings", lambda: _settings(EM_DB_PATH=str(db)))

    assert cli.main(["approve", "Q-PROS-1", "--approver", "dr_smith"]) == 0
    assert cli.main(["reject", "Q-PAT-1", "--approver", "dr_smith", "--reason", "off-label"]) == 0
    # Unknown id exits non-zero without raising.
    assert cli.main(["approve", "NOPE", "--approver", "dr_smith"]) == 1


def test_cli_reject_then_approve_conflicts(pending_store):
    cli.cmd_reject(pending_store, "Q-PROV-1", "dr_smith", "off-label")
    with pytest.raises(ApprovalError):
        cli.cmd_approve(pending_store, "Q-PROV-1", "dr_smith")
