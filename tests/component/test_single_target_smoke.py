"""Single-target / limited smoke run: verify ONE target end-to-end on a tiny input.

`run --target <id> --limit 1` dispatches one approved question to exactly one target, captures it,
and scores it — so you can confirm a freshly-fixed provider works (capture AND scoring) without
running the full bank. Everything here is offline/mock (no keys, no network).
"""

from __future__ import annotations

import pytest

from evidence_monitor import cli
from evidence_monitor.config.settings import Settings
from evidence_monitor.data_access.interface import QueryFilters
from evidence_monitor.data_access.models import (
    ApprovalStatus,
    Domain,
    Persona,
    Question,
    ResponseStatus,
)
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.response_repo.repository import ResponseService


def _settings(**kw: str) -> Settings:
    return Settings(_env_file=None, **kw)


@pytest.fixture
def store():
    s = SqliteStore(":memory:")
    for i in range(1, 4):  # three APPROVED + active questions (PROSPECT → served by all targets)
        s.questions.upsert(
            Question(
                question_id=f"Q-{i:03d}",
                question_text=f"Generic question {i}?",
                persona=Persona.PROSPECT,
                therapeutic_area="Area-One",
                brand_focus="Brand-X",
                domain=Domain.EFFICACY,
            )
        )
        s.questions.set_approval(f"Q-{i:03d}", ApprovalStatus.APPROVED, "rev")
    yield s
    s.close()


def _responses(store: SqliteStore):
    return ResponseService(store.responses).query(QueryFilters(), page_size=None).items


# --------------------------------------------------------------------------- #
# Target selection
# --------------------------------------------------------------------------- #
def test_select_one_target_by_id():
    chosen = cli._select_targets(_settings(), "openai-gpt4o")
    assert [t.target_id for t in chosen] == ["openai-gpt4o"]


def test_select_all_targets_when_unset():
    assert len(cli._select_targets(_settings(), None)) >= 3


def test_unknown_target_raises_clear_error():
    with pytest.raises(ValueError, match="unknown --target 'nope'"):
        cli._select_targets(_settings(), "nope")


# --------------------------------------------------------------------------- #
# One target, one question — captured AND scored
# --------------------------------------------------------------------------- #
def test_one_target_one_question_captures_and_scores(store):
    summary = cli.cmd_run(_settings(), store, mock=True, target_id="openai-gpt4o", limit=1)

    rows = _responses(store)
    assert len(rows) == 1  # exactly one (question × target) pair dispatched
    r = rows[0]
    assert r.target_id == "openai-gpt4o"  # only the chosen target was hit
    assert r.status is ResponseStatus.SUCCESS
    # Capture AND scoring both worked: a versioned ScoringRecord exists for the response (FR-015).
    score = store.scores.latest_for(r.response_id)
    assert score is not None and score.version >= 1
    assert summary.questions_attempted == 1 and summary.responses_captured == 1


def test_limit_caps_questions_across_active_targets(store):
    # No --target: limit alone caps questions; the full active fan-out applies to each.
    cli.cmd_run(_settings(), store, mock=True, limit=2)
    rows = _responses(store)
    assert len({r.question_id for r in rows}) == 2  # only 2 of the 3 approved questions
    assert all(store.scores.latest_for(r.response_id) is not None for r in rows)


def test_smoke_run_prints_capture_and_scoring_confirmation(store, capsys):
    cli.cmd_run(_settings(), store, mock=True, target_id="anthropic-claude-target", limit=1)
    out = capsys.readouterr().out
    assert "capture + scoring (this run):" in out
    assert "[SUCCESS]" in out and "anthropic-claude-target" in out
    assert "scored v1" in out


# --------------------------------------------------------------------------- #
# health-check skips inactive targets (never probed, never "live")
# --------------------------------------------------------------------------- #
def test_health_check_skips_inactive_targets():
    by_id = dict(cli.check_targets(_settings(), mock=True))
    assert by_id["open-evidence"].skipped is True
    assert by_id["openai-gpt4o"].skipped is False and by_id["openai-gpt4o"].reachable is True
