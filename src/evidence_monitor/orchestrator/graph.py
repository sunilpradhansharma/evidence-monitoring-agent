"""Explicit, code-defined LangGraph wiring of the run flow (Principle VIII — no autonomous loops).

The graph is fixed and inspectable:

    START → init_run → load_questions ─┐
                                       ▼  (cursor < len → dispatch)
                            dispatch_question ──↺ (more questions?) ──┐
                                       │ (done)                       │
                                       ▼ ◀───────────────────────────┘
                                  score_batch → evaluate_alerts → render_summary → END

The per-question loop is a single conditional edge back to ``dispatch_question``; control flow is
in code, not the model. :func:`run` compiles the graph and invokes it with a recursion limit sized
to the question count so the explicit loop is never mistaken for a runaway.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from evidence_monitor.data_access.models import TriggerType
from evidence_monitor.orchestrator.nodes import OrchestratorContext, build_nodes
from evidence_monitor.orchestrator.state import RunState

# Non-dispatch nodes that still consume a graph super-step; padded onto the recursion limit.
_FIXED_STEPS = 16


def build_graph(ctx: OrchestratorContext):
    """Compile the explicit run graph bound to ``ctx``."""
    nodes = build_nodes(ctx)
    graph = StateGraph(RunState)
    graph.add_node("init_run", nodes["init_run"])
    graph.add_node("load_questions", nodes["load_questions"])
    graph.add_node("dispatch_question", nodes["dispatch_question"])
    graph.add_node("score_batch", nodes["score_batch"])
    graph.add_node("evaluate_alerts", nodes["evaluate_alerts"])
    graph.add_node("render_summary", nodes["render_summary"])

    graph.add_edge(START, "init_run")
    graph.add_edge("init_run", "load_questions")
    # Loop edge: keep dispatching one question at a time until the cursor passes the last one.
    branches = {"dispatch": "dispatch_question", "done": "score_batch"}
    graph.add_conditional_edges("load_questions", nodes["more_questions"], branches)
    graph.add_conditional_edges("dispatch_question", nodes["more_questions"], branches)
    graph.add_edge("score_batch", "evaluate_alerts")
    graph.add_edge("evaluate_alerts", "render_summary")
    graph.add_edge("render_summary", END)
    return graph.compile()


def run(ctx: OrchestratorContext, *, trigger: TriggerType = TriggerType.SCHEDULED) -> RunState:
    """Execute one run (fresh or resumed via ``ctx.resume_run_id``) and return the final state."""
    app = build_graph(ctx)
    # Each approved question is one dispatch super-step; size the limit to the work plus the
    # fixed nodes so the explicit per-question loop is never clipped (default limit is 25).
    question_count = len(ctx.store.questions.approved_active())
    recursion_limit = max(25, question_count + _FIXED_STEPS)
    final = app.invoke(RunState(trigger=trigger), config={"recursion_limit": recursion_limit})
    return RunState(**final)


__all__ = ["build_graph", "run"]
