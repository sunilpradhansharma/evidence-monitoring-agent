"""Command-line entry point (``evidence-monitor``).

Commands:
- ``run`` — execute a full run over the approved question bank.
- ``dry-run`` — validate config + target connectivity and write NOTHING (no run, no DB writes).
- ``subset`` — run over a subset of approved questions filtered by persona / therapeutic area /
  domain.
- ``health-check`` — verify connectivity to every configured target.
- ``approve`` / ``reject`` — the scriptable path to the Medical Affairs approval workflow (the
  same gate the web Approvals tab drives); records the approver and appends an audit entry.

All targets, model ids, thresholds, the token budget, and the schedule come from config
(Principles V/VIII); ``--mock`` (or ``EM_OFFLINE_MOCK``) runs fully offline with deterministic
adapters. The command functions take an injected store/settings so they are unit-testable; only
:func:`main` builds the real SQLite store.
"""

from __future__ import annotations

import argparse
import sys

from evidence_monitor.alerts.rules import AlertThresholds
from evidence_monitor.config.settings import Settings, get_settings
from evidence_monitor.data_access.models import (
    AuditEventType,
    Domain,
    Persona,
    Question,
    TriggerType,
)
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.llm.adapters.base import HealthResult
from evidence_monitor.llm.client import ClaudeClient
from evidence_monitor.llm.registry import build_adapter, load_prices, load_targets
from evidence_monitor.observability.logging import get_logger, log_event
from evidence_monitor.orchestrator import OrchestratorContext, RunManager
from evidence_monitor.orchestrator import run as run_graph
from evidence_monitor.orchestrator.state import QuestionFilter, RunState, RunSummary
from evidence_monitor.question_repo.approval import ApprovalError, approval_audit_event
from evidence_monitor.question_repo.repository import QuestionService
from evidence_monitor.scoring.scorer import Scorer

_LOGGER = get_logger("evidence_monitor.cli")


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #
def build_context(
    settings: Settings,
    store: SqliteStore,
    *,
    mock: bool,
    question_filter: QuestionFilter | None = None,
) -> OrchestratorContext:
    """Assemble an :class:`OrchestratorContext` from config (targets, prices, thresholds, budget).

    The model id, targets, prices, alert thresholds, and token budget all come from ``settings``.
    """
    return OrchestratorContext(
        store=store,
        targets=load_targets(settings.targets_config_path),
        scorer=Scorer(ClaudeClient(model_id=settings.claude_model_id, mock=mock)),
        run_manager=RunManager(store.runs),
        thresholds=AlertThresholds(
            negative_sentiment=settings.negative_sentiment_threshold,
            competitor_margin=settings.competitor_sentiment_margin,
        ),
        mock=mock,
        prices=load_prices(settings.targets_config_path),
        max_tokens_per_run=settings.max_tokens_per_run,
        question_filter=question_filter,
    )


def check_targets(settings: Settings, *, mock: bool) -> list[tuple[str, HealthResult]]:
    """Build each configured target's adapter and probe its health (no store, no writes)."""
    return [
        (t.target_id, build_adapter(t, mock=mock).health())
        for t in load_targets(settings.targets_config_path)
    ]


# --------------------------------------------------------------------------- #
# Commands (return values for testability; printing is a side effect)
# --------------------------------------------------------------------------- #
def cmd_run(
    settings: Settings,
    store: SqliteStore,
    *,
    mock: bool,
    question_filter: QuestionFilter | None = None,
) -> RunSummary:
    """Execute a run (optionally a subset) and return its summary."""
    ctx = build_context(settings, store, mock=mock, question_filter=question_filter)
    state: RunState = run_graph(ctx, trigger=TriggerType.ADHOC)
    summary = state.summary
    log_event(
        _LOGGER,
        "INFO",
        "run complete",
        run_id=summary.run_id,
        responses_by_status=summary.responses_by_status,
        alerts=summary.alert_count,
        total_tokens=summary.total_tokens,
        est_cost=summary.est_cost,
        budget_exhausted=summary.budget_exhausted,
    )
    print(_format_summary(summary))
    return summary


def cmd_health_check(settings: Settings, *, mock: bool) -> bool:
    """Probe every configured target; return True iff all are reachable."""
    results = check_targets(settings, mock=mock)
    all_ok = all(h.reachable for _, h in results)
    for target_id, health in results:
        print(f"[{'OK ' if health.reachable else 'FAIL'}] {target_id}: {health.detail}")
    print("health-check: " + ("all targets reachable" if all_ok else "one or more UNREACHABLE"))
    return all_ok


def cmd_dry_run(settings: Settings, *, mock: bool) -> bool:
    """Validate config + connectivity without writing anything; return True iff valid."""
    targets = load_targets(settings.targets_config_path)  # parses/validates the targets config
    print(f"config OK: {len(targets)} target(s) loaded from {settings.targets_config_path}")
    ok = cmd_health_check(settings, mock=mock)
    print("dry-run: validated, wrote nothing")
    return ok


def cmd_approve(store: SqliteStore, question_id: str, approver: str) -> Question:
    """Approve a question through the shared workflow + append an audit entry (scriptable path)."""
    question = QuestionService(store.questions).approve(question_id, approver)
    store.audit.append(
        approval_audit_event(
            event_type=AuditEventType.QUESTION_APPROVED,
            question_id=question_id,
            approver=approver,
        )
    )
    print(f"approved {question_id} (v{question.version}) by {approver}")
    return question


def cmd_reject(store: SqliteStore, question_id: str, approver: str, reason: str) -> Question:
    """Reject a question through the shared workflow + append an audit entry (scriptable path)."""
    question = QuestionService(store.questions).reject(question_id, approver, reason)
    store.audit.append(
        approval_audit_event(
            event_type=AuditEventType.QUESTION_REJECTED,
            question_id=question_id,
            approver=approver,
            reason=reason,
        )
    )
    print(f"rejected {question_id} (v{question.version}) by {approver}: {reason}")
    return question


def _format_summary(s: RunSummary) -> str:
    lines = [
        f"run {s.run_id}",
        f"  questions attempted : {s.questions_attempted}",
        f"  responses by status : {s.responses_by_status}",
        f"  responses captured  : {s.responses_captured}",
        f"  alerts              : {s.alert_count}",
        f"  total tokens        : {s.total_tokens}",
        f"  estimated cost (USD): {s.est_cost:.6f}",
    ]
    if s.budget_exhausted:
        lines.append("  ** PAUSED: token budget reached — rerun to resume the remaining bank **")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evidence-monitor", description="Evidence Monitoring Agent"
    )
    parser.add_argument(
        "--mock", action="store_true", help="run offline with deterministic adapters"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="run the full approved question bank")
    sub.add_parser("dry-run", help="validate config + connectivity; write nothing")
    sub.add_parser("health-check", help="verify connectivity to all configured targets")

    subset = sub.add_parser("subset", help="run a subset of approved questions")
    subset.add_argument("--persona", choices=[p.value for p in Persona])
    subset.add_argument("--therapeutic-area")
    subset.add_argument("--domain", choices=[d.value for d in Domain])

    approve = sub.add_parser("approve", help="approve a question (Medical Affairs gate)")
    approve.add_argument("question_id")
    approve.add_argument("--approver", required=True, help="approver name (recorded, SE-002)")

    reject = sub.add_parser("reject", help="reject a question (terminal; excluded from runs)")
    reject.add_argument("question_id")
    reject.add_argument("--approver", required=True, help="approver name (recorded, SE-002)")
    reject.add_argument("--reason", required=True, help="rejection reason (recorded)")
    return parser


def _subset_filter(args: argparse.Namespace) -> QuestionFilter:
    return QuestionFilter(
        persona=Persona(args.persona) if args.persona else None,
        therapeutic_area=args.therapeutic_area,
        domain=Domain(args.domain) if args.domain else None,
    )


def main(argv: list[str] | None = None) -> int:
    """Console entry point. Returns a process exit code."""
    args = _build_parser().parse_args(argv)
    settings = get_settings()
    mock = bool(args.mock) or settings.offline_mock

    if args.command in ("run", "subset"):
        store = SqliteStore(settings.db_path)
        try:
            question_filter = _subset_filter(args) if args.command == "subset" else None
            cmd_run(settings, store, mock=mock, question_filter=question_filter)
        finally:
            store.close()
        return 0

    if args.command in ("approve", "reject"):
        store = SqliteStore(settings.db_path)
        try:
            if args.command == "approve":
                cmd_approve(store, args.question_id, args.approver)
            else:
                cmd_reject(store, args.question_id, args.approver, args.reason)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        except ApprovalError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        finally:
            store.close()
        return 0

    ok = (
        cmd_dry_run(settings, mock=mock)
        if args.command == "dry-run"
        else cmd_health_check(settings, mock=mock)
    )
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = [
    "build_context",
    "check_targets",
    "cmd_approve",
    "cmd_dry_run",
    "cmd_health_check",
    "cmd_reject",
    "cmd_run",
    "main",
]
