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
from evidence_monitor.data_access.models import ApprovalStatus, Domain, Persona
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.orchestrator.state import QuestionFilter, RunSummary
from evidence_monitor.response_repo.repository import ResponseService

TARGETS_CFG = str(
    Path(__file__).resolve().parents[2] / "src/evidence_monitor/config/targets.yaml"
)


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
    assert summary.responses_by_status == {"SUCCESS": 9}  # 3 questions × 3 active targets
    assert summary.responses_captured == 9
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
    assert summary.responses_captured == 3


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
    monkeypatch.setattr(
        cli, "get_settings", lambda: _settings(EM_DB_PATH=str(tmp_path / "e.db"))
    )
    assert cli.main(["--mock", "health-check"]) == 0
    assert cli.main(["--mock", "dry-run"]) == 0
    assert cli.main(["--mock", "run"]) == 0
    assert cli.main(["--mock", "subset", "--persona", "PROVIDER", "--domain", "SAFETY"]) == 0
