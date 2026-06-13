"""The orchestration run state (the LangGraph state schema).

:class:`RunState` is the single object threaded through the explicit graph in ``graph.py``. Every
node receives it and returns a partial update; LangGraph merges updates with last-value semantics,
so accumulating nodes return the full updated list (e.g. ``responses + new``). The state holds
only data — never the store, adapters, or scorer; those injected dependencies live in
``nodes.OrchestratorContext`` so the state stays a plain, inspectable value object.

Content-agnostic (Principle IV): brand / therapeutic-area / domain values ride through inside the
carried :class:`Question` / :class:`Response` objects as opaque data; nothing is enumerated here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from evidence_monitor.data_access.models import (
    Alert,
    LLMTarget,
    Question,
    ScoringRecord,
    TriggerType,
)
from evidence_monitor.response_repo.schema import Response


@dataclass
class RunSummary:
    """End-of-run summary (FR-026) — what the dashboard renders and the run record finalizes."""

    run_id: str
    trigger: TriggerType
    started_at: datetime | None
    ended_at: datetime | None
    questions_attempted: int
    responses_by_status: dict[str, int]
    responses_captured: int  # SUCCESS count
    failure_count: int
    alert_count: int
    total_tokens: int


@dataclass
class RunState:
    """Mutable-by-merge state for one orchestration run (the LangGraph state schema)."""

    trigger: TriggerType = TriggerType.SCHEDULED
    run_id: str | None = None
    targets: list[LLMTarget] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    cursor: int = 0  # index of the next question to dispatch (the resume point)
    responses: list[Response] = field(default_factory=list)
    scores: list[ScoringRecord] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    total_tokens: int = 0
    summary: RunSummary | None = None


__all__ = ["RunState", "RunSummary"]
