"""End-to-end mock run over the real seed bank (quickstart scenarios 1–5).

Exercises the whole pipeline with NO network and NO API keys: import the curated
``data/question_bank.csv`` → approve it → run the explicit LangGraph flow in deterministic
OFFLINE/MOCK mode → score → evaluate alerts → render the self-contained dashboard and CSV/JSON
exports. The assertions trace to the spec's success criteria:

- **SC-001 / SC-003** — the run completes unattended and ≥95% of attempts are captured.
- **US1 / Principle II** — one immutable response per (APPROVED question × eligible target); the
  conditional Open Evidence target never fires; an append-only audit entry per query/response.
- **US2 / Principle VII** — every capturable response gets a versioned scoring record carrying its
  evidence (brands, ≤5 claims, rationale).
- **SC-005** — captured responses are retrievable by each supported query dimension.
- **US5** — a self-contained dashboard HTML plus CSV and JSON exports are produced.

Content-agnostic (Principle IV): nothing here enumerates a brand / competitor / therapeutic area;
the seed's values flow through as opaque data.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_monitor.alerts.rules import AlertThresholds
from evidence_monitor.dashboard.render import write_static_report
from evidence_monitor.data_access.interface import QueryFilters
from evidence_monitor.data_access.models import ApprovalStatus, AuditEventType, TriggerType
from evidence_monitor.data_access.queries import to_csv, to_json
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.llm.client import ClaudeClient
from evidence_monitor.llm.registry import load_prices, load_targets, targets_for_persona
from evidence_monitor.orchestrator import OrchestratorContext, RunManager, run
from evidence_monitor.question_repo.importer import import_questions
from evidence_monitor.response_repo.repository import ResponseService
from evidence_monitor.response_repo.schema import ResponseStatus
from evidence_monitor.scoring.scorer import Scorer

_ROOT = Path(__file__).resolve().parents[2]
_SEED_CSV = _ROOT / "data/question_bank.csv"
_TARGETS_CFG = _ROOT / "src/evidence_monitor/config/targets.yaml"
# A capturable attempt is one that produced a usable answer (SC-003 numerator).
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


def _seed_and_approve(store: SqliteStore) -> int:
    """Import the real curated bank (PENDING) then approve every question. Returns the count."""
    report = import_questions(store.questions, _SEED_CSV)
    assert report.created >= 100, "seed bank should hold the full curated set"
    approved = 0
    for q in store.questions.list():
        store.questions.set_approval(q.question_id, ApprovalStatus.APPROVED, "ma_reviewer")
        approved += 1
    return approved


def _context(store, targets) -> OrchestratorContext:
    return OrchestratorContext(
        store=store,
        targets=targets,
        scorer=Scorer(ClaudeClient(model_id="scorer-model-1", mock=True)),
        run_manager=RunManager(store.runs),
        thresholds=AlertThresholds(),
        mock=True,
        prices=load_prices(_TARGETS_CFG),
    )


def _expected_pairs(store, targets) -> set[tuple[str, str]]:
    return {
        (q.question_id, t.target_id)
        for q in store.questions.approved_active()
        for t in targets_for_persona(targets, q.persona)
    }


# --------------------------------------------------------------------------- #
# Scenarios 1 & 2 — capture, immutability, audit, scoring
# --------------------------------------------------------------------------- #
def test_full_seed_run_captures_scores_and_summarizes(store, targets):
    _seed_and_approve(store)
    expected_pairs = _expected_pairs(store, targets)
    assert len(expected_pairs) >= 300  # ~100+ questions × 3 unconditional targets (FR-006)

    final = run(_context(store, targets), trigger=TriggerType.SCHEDULED)

    # US1 — exactly one immutable response per (question × eligible target); no Open Evidence.
    produced = {(r.question_id, r.target_id) for r in final.responses}
    assert produced == expected_pairs
    assert "open-evidence" not in {r.target_id for r in final.responses}

    # SC-003 — ≥95% successful capture across targets (mock SUCCESS path → 100%).
    captured = sum(1 for r in final.responses if r.status in _CAPTURED)
    assert captured / len(final.responses) >= 0.95
    assert final.summary.responses_by_status == {str(ResponseStatus.SUCCESS): len(final.responses)}

    # US2 / Principle VII — every capturable response has a versioned score carrying its evidence.
    assert len(final.scores) == len(final.responses)
    for response in final.responses:
        score = store.scores.latest_for(response.response_id)
        assert score is not None
        assert score.version >= 1
        assert score.scoring_rationale  # rationale present
        assert len(score.key_claims) <= 5  # ≤5 key claims (Principle VII)

    # FR-026 — run summary is populated and the run record is finalized.
    assert final.summary.questions_attempted == len(store.questions.approved_active())
    assert final.summary.responses_captured == len(final.responses)
    assert final.summary.total_tokens > 0
    assert store.runs.get(final.run_id).ended_at is not None


def test_full_seed_run_is_unattended_and_audited(store, targets):
    """SC-001 — the run completes with no manual intervention and writes a complete audit trail."""
    _seed_and_approve(store)
    final = run(_context(store, targets))

    counts: dict[str, int] = {}
    for row in store.connection.execute(
        "SELECT event_type, COUNT(*) FROM audit_log GROUP BY event_type"
    ):
        counts[row[0]] = row[1]

    n = len(final.responses)
    assert counts[str(AuditEventType.RUN_STARTED)] == 1
    assert counts[str(AuditEventType.RUN_ENDED)] == 1
    assert counts[str(AuditEventType.QUERY_DISPATCHED)] == n
    assert counts[str(AuditEventType.RESPONSE_RECEIVED)] == n


def test_responses_are_immutable_after_scoring(store, targets):
    """Principle II — scoring never mutates the stored response (re-read is byte-identical)."""
    _seed_and_approve(store)
    final = run(_context(store, targets))

    sample = final.responses[0]
    reread = ResponseService(store.responses).get(sample.response_id)
    assert reread is not None
    assert reread.response_text == sample.response_text
    assert reread.status == sample.status
    assert reread.response_tokens == sample.response_tokens


# --------------------------------------------------------------------------- #
# Scenario 5 — query dimensions, dashboard, exports
# --------------------------------------------------------------------------- #
def test_responses_queryable_by_every_dimension(store, targets):
    """SC-005 — captured responses are retrievable across each supported query dimension."""
    _seed_and_approve(store)
    run(_context(store, targets))
    responses = ResponseService(store.responses)
    sample = responses.query(QueryFilters(), page_size=None).items[0]

    for filters in (
        QueryFilters(llm=sample.llm_name),
        QueryFilters(persona=sample.persona),
        QueryFilters(therapeutic_area=sample.therapeutic_area),
        QueryFilters(brand=sample.brand_focus),
        QueryFilters(domain=str(sample.domain)),
        QueryFilters(status=ResponseStatus.SUCCESS),
    ):
        page = responses.query(filters, page_size=None)
        assert page.items, f"expected matches for {filters}"


def test_dashboard_and_exports_are_produced(store, targets, tmp_path):
    """US5 / FR-023/FR-025 — a self-contained dashboard plus CSV and JSON exports are written."""
    _seed_and_approve(store)
    run(_context(store, targets))

    out = write_static_report(store, tmp_path / "dashboard.html", generated_at="2026-06-13T00:00Z")
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    # Self-contained (inline styles, no external assets) with the Reports sections present.
    assert "<style" in html and "<link" not in html
    for marker in (
        "Sentiment by model",
        "Competitive positioning",
        "Alerts",
        "volume over time",
    ):
        assert marker in html

    rows = ResponseService(store.responses).query(QueryFilters(), page_size=None).items
    csv_text = to_csv(rows)
    json_text = to_json(rows)
    assert csv_text.count("\n") >= len(rows)  # header + one line per row
    assert len(json.loads(json_text)) == len(rows)
