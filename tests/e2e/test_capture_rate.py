"""End-to-end capture-rate guarantee (SC-003 / Principle IX) over the seed bank, offline.

Two properties the constitution makes non-negotiable:

1. **≥95% successful capture.** A clean mock run over the full approved bank captures every
   attempt (100%), comfortably clearing the ≥95% bar.
2. **A flaky target never sinks the run.** With one target failing a small, deterministic fraction
   of its calls (transient failures that exhaust the retry budget → FAILED), the run still
   completes unattended, the failures are recorded as FAILED (not lost, not retried forever), and
   overall capture stays ≥95%. A resumed run then picks up exactly where it left off with no
   duplicate submissions.

Everything runs in deterministic OFFLINE/MOCK mode — no network, no keys, reproducible.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evidence_monitor.alerts.rules import AlertThresholds
from evidence_monitor.data_access.interface import QueryFilters
from evidence_monitor.data_access.models import ApprovalStatus, TriggerType
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.llm.adapters.base import (
    AdapterResult,
    FinishReason,
    HealthResult,
    LLMAdapter,
    ResponseStatus,
)
from evidence_monitor.llm.client import ClaudeClient
from evidence_monitor.llm.registry import load_targets, targets_for_persona
from evidence_monitor.orchestrator import OrchestratorContext, RunManager, run
from evidence_monitor.question_repo.importer import import_questions
from evidence_monitor.response_repo.repository import ResponseService
from evidence_monitor.scoring.scorer import Scorer

_ROOT = Path(__file__).resolve().parents[2]
_SEED_CSV = _ROOT / "data/question_bank.csv"
_TARGETS_CFG = _ROOT / "src/evidence_monitor/config/targets.yaml"
_CAPTURED = (ResponseStatus.SUCCESS, ResponseStatus.TRUNCATED)


@pytest.fixture
def store():
    s = SqliteStore(":memory:")
    yield s
    s.close()


@pytest.fixture
def targets():
    # Disable per-target rate limiting so a full-seed mock run needs no real wall-clock sleeps
    # (rate limiting is covered by its own unit test). model_copy keeps active/personas intact.
    return [t.model_copy(update={"rpm_limit": 0}) for t in load_targets(_TARGETS_CFG)]


def _seed_and_approve(store: SqliteStore) -> None:
    import_questions(store.questions, _SEED_CSV)
    for q in store.questions.list():
        store.questions.set_approval(q.question_id, ApprovalStatus.APPROVED, "ma_reviewer")


def _context(store, targets, **kwargs) -> OrchestratorContext:
    return OrchestratorContext(
        store=store,
        targets=targets,
        scorer=Scorer(ClaudeClient(model_id="scorer-model-1", mock=True)),
        run_manager=RunManager(store.runs),
        thresholds=AlertThresholds(),
        mock=True,
        **kwargs,
    )


def _capture_rate(responses) -> float:
    captured = sum(1 for r in responses if r.status in _CAPTURED)
    return captured / len(responses)


class _FlakyAdapter:
    """Wraps a real mock adapter, forcing FAILED on every ``fail_every``-th call (the rest pass).

    Models a target whose retry budget is exhausted on a sporadic subset of calls — exactly the
    Principle IX path: the engine marks the record FAILED and the run continues to the next.
    """

    def __init__(self, inner: LLMAdapter, *, fail_every: int) -> None:
        self._inner = inner
        self._fail_every = fail_every
        self._calls = 0
        self.target_id = inner.target_id
        self.name = inner.name
        self.failures = 0

    def submit(self, **kwargs) -> AdapterResult:
        self._calls += 1
        if self._calls % self._fail_every == 0:
            self.failures += 1
            return AdapterResult(
                status=ResponseStatus.FAILED,
                response_text="",
                response_tokens=0,
                finish_reason=FinishReason.ERROR,
                model_version=self._inner.name,
                block_reason=None,
                attempts=3,
            )
        return self._inner.submit(**kwargs)

    def health(self) -> HealthResult:
        return self._inner.health()


# --------------------------------------------------------------------------- #
# 1. Clean run — full capture
# --------------------------------------------------------------------------- #
def test_clean_run_captures_at_least_95_percent(store, targets):
    _seed_and_approve(store)
    final = run(_context(store, targets), trigger=TriggerType.SCHEDULED)

    assert _capture_rate(final.responses) == 1.0  # mock SUCCESS path captures everything
    assert final.summary.failure_count == 0
    assert final.summary.responses_captured == len(final.responses)


# --------------------------------------------------------------------------- #
# 2. Flaky target — run survives, failures recorded, still ≥95%
# --------------------------------------------------------------------------- #
def test_flaky_target_does_not_sink_the_run(store, targets):
    _seed_and_approve(store)
    ctx = _context(store, targets)

    # Make one unconditional target fail ~1 in 30 of its calls (a few FAILED across the run).
    flaky_id = "google-gemini"
    flaky = _FlakyAdapter(ctx.adapters[flaky_id], fail_every=30)
    ctx.adapters[flaky_id] = flaky

    final = run(ctx)

    # The run completed unattended over the whole bank despite the failures.
    assert final.summary.questions_attempted == len(store.questions.approved_active())
    assert flaky.failures > 0, "the flaky target should have produced some FAILED records"

    # Failures are recorded as FAILED (not lost), and capture still clears the ≥95% bar (SC-003).
    failed = [r for r in final.responses if r.status == ResponseStatus.FAILED]
    assert len(failed) == flaky.failures
    assert final.summary.failure_count == flaky.failures
    assert _capture_rate(final.responses) >= 0.95

    # FAILED responses carry no answer, so they are not scored (only capturable text is).
    for r in failed:
        assert store.scores.latest_for(r.response_id) is None


# --------------------------------------------------------------------------- #
# 3. Resume — pick up from the last completed question, no duplicates
# --------------------------------------------------------------------------- #
def test_interrupted_run_resumes_without_duplicates(store, targets):
    _seed_and_approve(store)
    approved = store.questions.approved_active()

    # Start a run and simulate an interruption after the first question's responses persisted.
    started = RunManager(store.runs).start(TriggerType.SCHEDULED)
    first = approved[0]
    responses = ResponseService(store.responses)
    for target in targets_for_persona(targets, first.persona):
        from evidence_monitor.llm.registry import build_adapter
        from evidence_monitor.response_repo.schema import Response

        result = build_adapter(target, mock=True).submit(
            question_text=first.question_text,
            persona=first.persona,
            system_prompt="You are a helpful assistant.",
        )
        responses.record(
            Response(
                run_id=started.run_id,
                question_id=first.question_id,
                target_id=target.target_id,
                llm_name=target.llm_name,
                llm_model_version=result.model_version,
                persona=first.persona,
                therapeutic_area=first.therapeutic_area,
                brand_focus=first.brand_focus,
                domain=first.domain,
                response_text=result.response_text,
                response_tokens=result.response_tokens,
                finish_reason=result.finish_reason,
                status=result.status,
                block_reason=result.block_reason,
            )
        )
    RunManager(store.runs).checkpoint(started.run_id, first.question_id)
    before = len(responses.query(QueryFilters(run_id=started.run_id), page_size=None).items)

    # Resume the SAME run.
    final = run(_context(store, targets, resume_run_id=started.run_id))

    assert final.run_id == started.run_id  # no new run created
    assert first.question_id not in {r.question_id for r in final.responses}  # not re-submitted

    # The store holds exactly one full fan-out per approved question — no duplicates.
    all_rows = responses.query(QueryFilters(run_id=started.run_id), page_size=None).items
    per_question: dict[str, int] = {}
    for r in all_rows:
        per_question[r.question_id] = per_question.get(r.question_id, 0) + 1
    assert per_question[first.question_id] == before  # untouched
    assert max(per_question.values()) == min(per_question.values())  # uniform fan-out, no dups
