"""The graph nodes and the dependency context they close over.

Nodes are pure-ish functions of :class:`RunState` that return partial updates (LangGraph merges
them). All injected dependencies — the store, per-target adapters, the scorer, the run manager,
and alert thresholds — live on :class:`OrchestratorContext`, never in the state, so the state
stays an inspectable value object. The node set realizes the explicit flow:

    init_run → load_questions → (dispatch_question ↺ per question) → score_batch
             → evaluate_alerts → render_summary

Constitution alignment: adapters run in deterministic OFFLINE/MOCK mode for offline runs
(Principle XI); the run checkpoints after each question's responses persist (Principle IX); the
scorer only scores and code (``alerts.rules``) decides alerts (Principle VIII); every dispatch
and response is written to the append-only audit log (Principle II / FR-013).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from evidence_monitor.alerts import rules
from evidence_monitor.alerts.rules import AlertThresholds
from evidence_monitor.data_access.interface import RunTotals
from evidence_monitor.data_access.models import (
    Alert,
    AuditEvent,
    AuditEventType,
    LLMTarget,
    ResponseStatus,
)
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.llm.adapters.base import LLMAdapter, MockBehavior
from evidence_monitor.llm.registry import build_adapter, targets_for_persona
from evidence_monitor.orchestrator.run_manager import RunManager
from evidence_monitor.orchestrator.state import RunState, RunSummary
from evidence_monitor.response_repo.repository import ResponseService
from evidence_monitor.response_repo.schema import Response
from evidence_monitor.scoring.scorer import Scorer

# Capturable statuses worth scoring (have meaningful text); FAILED/BLOCKED carry no answer.
_SCORABLE = (ResponseStatus.SUCCESS, ResponseStatus.TRUNCATED)
# Generic, content-agnostic end-user prompt for the monitored targets (no brand/drug names).
_TARGET_SYSTEM_PROMPT = "You are a helpful assistant. Answer the user's question."

# Conditional-edge labels for the per-question loop.
_DISPATCH = "dispatch"
_DONE = "done"


@dataclass
class OrchestratorContext:
    """Injected dependencies shared by all nodes (kept out of the serializable run state)."""

    store: SqliteStore
    targets: list[LLMTarget]
    scorer: Scorer
    run_manager: RunManager
    thresholds: AlertThresholds = field(default_factory=AlertThresholds)
    mock: bool = True
    mock_behavior: MockBehavior = MockBehavior.SUCCESS
    resume_run_id: str | None = None

    def __post_init__(self) -> None:
        # Build one adapter per target up front (OFFLINE/MOCK so runs need no network or key).
        self.adapters: dict[str, LLMAdapter] = {
            t.target_id: build_adapter(t, mock=self.mock, mock_behavior=self.mock_behavior)
            for t in self.targets
        }
        self.responses = ResponseService(self.store.responses)


def build_nodes(ctx: OrchestratorContext) -> dict[str, Callable]:
    """Return the node callables (and the loop predicate) bound to ``ctx``."""

    def init_run(state: RunState) -> dict:
        """Assign a run id (or adopt the one being resumed) and announce the run start."""
        if ctx.resume_run_id is not None:
            run = ctx.store.runs.get(ctx.resume_run_id)
            if run is None:
                raise ValueError(f"cannot resume unknown run {ctx.resume_run_id!r}")
        else:
            run = ctx.run_manager.start(state.trigger)
        ctx.store.audit.append(
            AuditEvent(
                run_id=run.run_id,
                event_type=AuditEventType.RUN_STARTED,
                role="ORCHESTRATOR",
                target="run",
                detail="run started",
            )
        )
        return {"run_id": run.run_id, "targets": ctx.targets}

    def load_questions(state: RunState) -> dict:
        """Load the APPROVED + active question set and the resume cursor (FR-003, IX)."""
        questions = ctx.store.questions.approved_active()
        cursor = (
            ctx.run_manager.resume_point(state.run_id, questions)
            if ctx.resume_run_id is not None
            else 0
        )
        return {"questions": questions, "cursor": cursor}

    def more_questions(state: RunState) -> str:
        """Loop predicate: dispatch the next question, or fall through to scoring."""
        return _DISPATCH if state.cursor < len(state.questions) else _DONE

    def dispatch_question(state: RunState) -> dict:
        """Submit ONE question to every eligible target, persist each response, checkpoint."""
        question = state.questions[state.cursor]
        eligible = targets_for_persona(ctx.targets, question.persona)
        new_responses: list[Response] = []
        tokens = 0

        for target in eligible:
            label = f"{target.llm_name}:{question.question_id}"
            ctx.store.audit.append(
                AuditEvent(
                    run_id=state.run_id,
                    event_type=AuditEventType.QUERY_DISPATCHED,
                    role="TARGET",
                    target=label,
                    detail="dispatched",
                )
            )
            result = ctx.adapters[target.target_id].submit(
                question_text=question.question_text,
                persona=question.persona,
                system_prompt=_TARGET_SYSTEM_PROMPT,
            )
            response = Response(
                run_id=state.run_id,
                question_id=question.question_id,
                target_id=target.target_id,
                llm_name=target.llm_name,
                llm_model_version=result.model_version,
                persona=question.persona,
                therapeutic_area=question.therapeutic_area,
                brand_focus=question.brand_focus,
                domain=question.domain,
                response_text=result.response_text,
                response_tokens=result.response_tokens,
                finish_reason=result.finish_reason,
                status=result.status,
                block_reason=result.block_reason,
            )
            ctx.responses.record(response)  # immutable, write-once (Principle II)
            ctx.store.audit.append(
                AuditEvent(
                    run_id=state.run_id,
                    event_type=AuditEventType.RESPONSE_RECEIVED,
                    role="TARGET",
                    target=label,
                    detail=str(result.status),
                )
            )
            new_responses.append(response)
            tokens += result.response_tokens

        # Checkpoint AFTER all of this question's responses are persisted (Principle IX).
        ctx.run_manager.checkpoint(state.run_id, question.question_id)
        return {
            "responses": state.responses + new_responses,
            "cursor": state.cursor + 1,
            "total_tokens": state.total_tokens + tokens,
        }

    def score_batch(state: RunState) -> dict:
        """Score each capturable response into a separate, versioned scoring record (US2)."""
        new_scores = []
        tokens = 0
        for response in state.responses:
            if response.status not in _SCORABLE:
                continue
            scored = ctx.scorer.score(response)
            stored = ctx.store.scores.add_version(scored.record)
            new_scores.append(stored)
            tokens += scored.tokens
        return {"scores": state.scores + new_scores, "total_tokens": state.total_tokens + tokens}

    def evaluate_alerts(state: RunState) -> dict:
        """Apply deterministic threshold rules; raise an alert per fired rule (US4)."""
        new_alerts = []
        for score in state.scores:
            for fired in rules.evaluate(score, thresholds=ctx.thresholds):
                alert = Alert.for_rule(
                    score_id=score.score_id,
                    response_id=score.response_id,
                    rule=fired.rule,
                    reason=fired.reason,
                )
                ctx.store.alerts.insert(alert)
                new_alerts.append(alert)
        return {"alerts": state.alerts + new_alerts}

    def render_summary(state: RunState) -> dict:
        """Build the run summary and finalize the run record (FR-026)."""
        by_status = Counter(str(r.status) for r in state.responses)
        captured = by_status.get(str(ResponseStatus.SUCCESS), 0)
        failures = by_status.get(str(ResponseStatus.FAILED), 0)
        run = ctx.store.runs.get(state.run_id)
        summary = RunSummary(
            run_id=state.run_id,
            trigger=state.trigger,
            started_at=run.started_at if run else None,
            ended_at=datetime.now(UTC),
            questions_attempted=len(state.questions),
            responses_by_status=dict(by_status),
            responses_captured=captured,
            failure_count=failures,
            alert_count=len(state.alerts),
            total_tokens=state.total_tokens,
        )
        ctx.run_manager.finalize(
            state.run_id,
            RunTotals(
                questions_attempted=len(state.questions),
                responses_captured=captured,
                failure_count=failures,
                total_tokens=state.total_tokens,
                est_cost=0.0,
            ),
        )
        ctx.store.audit.append(
            AuditEvent(
                run_id=state.run_id,
                event_type=AuditEventType.RUN_ENDED,
                role="ORCHESTRATOR",
                target="run",
                detail="run ended",
            )
        )
        return {"summary": summary}

    return {
        "init_run": init_run,
        "load_questions": load_questions,
        "dispatch_question": dispatch_question,
        "score_batch": score_batch,
        "evaluate_alerts": evaluate_alerts,
        "render_summary": render_summary,
        "more_questions": more_questions,
    }


__all__ = ["OrchestratorContext", "build_nodes"]
