"""Run lifecycle: assign a run id, checkpoint progress, and resume from the last completed question.

Implements the resumability guarantee (Principle IX): the orchestrator checkpoints after every
question's responses are persisted, so an interrupted run can resume from exactly the next
question without re-submitting completed ones. This is a thin coordinator over the
``RunRepository`` seam — it owns no SQL and no provider calls.
"""

from __future__ import annotations

from evidence_monitor.data_access.interface import RunRepository, RunTotals
from evidence_monitor.data_access.models import Question, Run, TriggerType


class RunManager:
    """Assign run ids, checkpoint after each persist, and compute the resume cursor."""

    def __init__(self, runs: RunRepository) -> None:
        self._runs = runs

    def start(self, trigger: TriggerType) -> Run:
        """Create a fresh run (assigns the run id)."""
        return self._runs.create(trigger)

    def checkpoint(self, run_id: str, question_id: str) -> None:
        """Record the last fully-persisted question as the resume point (Principle IX)."""
        self._runs.checkpoint(run_id, question_id)

    def resume_point(self, run_id: str, questions: list[Question]) -> int:
        """The cursor to resume at: index just past the last completed question.

        Returns 0 (start from the beginning) when the run is unknown, has no checkpoint, or its
        checkpoint is not in the current approved set (e.g. that question was since rejected).
        ``questions`` MUST be the same ordering the run dispatches in, so the index is stable.
        """
        run = self._runs.get(run_id)
        if run is None or run.last_completed_question_id is None:
            return 0
        ids = [q.question_id for q in questions]
        try:
            return ids.index(run.last_completed_question_id) + 1
        except ValueError:
            return 0

    def finalize(self, run_id: str, totals: RunTotals) -> Run:
        """Write the run's final counters and end time."""
        return self._runs.finalize(run_id, totals)


__all__ = ["RunManager"]
