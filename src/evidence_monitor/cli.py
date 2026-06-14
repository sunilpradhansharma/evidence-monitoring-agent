"""Command-line entry point (``evidence-monitor``).

Commands:
- ``run`` — execute a full run over the approved question bank.
- ``import-questions`` — import a curated CSV/Excel bank as PENDING (idempotent upsert by id).
- ``dry-run`` — validate config + target connectivity and write NOTHING (no run, no DB writes).
- ``subset`` — run over a subset of approved questions filtered by persona / therapeutic area /
  domain.
- ``health-check`` — verify connectivity to every configured target.
- ``approve`` / ``reject`` — the scriptable path to the Medical Affairs approval workflow (the
  same gate the web Approvals tab drives); records the approver and appends an audit entry.
- ``approve-all-test-numbered`` / ``reset-to-pending`` — TEST-only bulk helpers (not the formal
  MA sign-off): approve every active question with a numbered approver/note, or reset all to
  PENDING. Both go through the repository approval seam + audit log, never raw SQL.

All targets, model ids, thresholds, the token budget, and the schedule come from config
(Principles V/VIII); ``--mock`` (or ``EM_OFFLINE_MOCK``) runs fully offline with deterministic
adapters. The command functions take an injected store/settings so they are unit-testable; only
:func:`main` builds the real SQLite store.
"""

from __future__ import annotations

import argparse
import sys

from evidence_monitor.alerts.rules import AlertThresholds
from evidence_monitor.config.settings import (
    Settings,
    apply_credentials_to_environment,
    credential_preflight,
    get_settings,
)
from evidence_monitor.data_access.models import (
    ApprovalStatus,
    AuditEventType,
    Domain,
    Persona,
    Question,
    ResponseStatus,
    TriggerType,
)
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.llm.adapters.base import HealthResult
from evidence_monitor.llm.adapters.provider_evidence_dev import (
    DISPLAY_NAME as _PROVIDER_EVIDENCE_DEV_NAME,
)
from evidence_monitor.llm.client import ClaudeClient
from evidence_monitor.llm.registry import build_adapter, load_prices, load_targets
from evidence_monitor.observability.logging import get_logger, log_event, register_secret
from evidence_monitor.orchestrator import OrchestratorContext, RunManager
from evidence_monitor.orchestrator import run as run_graph
from evidence_monitor.orchestrator.state import QuestionFilter, RunState, RunSummary
from evidence_monitor.question_repo.approval import ApprovalError, approval_audit_event
from evidence_monitor.question_repo.importer import ImportReport, import_questions
from evidence_monitor.question_repo.repository import QuestionService
from evidence_monitor.scoring.scorer import Scorer

_LOGGER = get_logger("evidence_monitor.cli")

# Display names for targets whose id slug should not be shown raw (structural labels, not regulated
# content). Keeps the dev stand-in shown as "Provider evidence (dev)" — never as "Open Evidence".
_TARGET_DISPLAY: dict[str, str] = {"provider-evidence-dev": _PROVIDER_EVIDENCE_DEV_NAME}


def _target_display(target_id: str) -> str:
    return _TARGET_DISPLAY.get(target_id, target_id)


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #
def _select_targets(settings: Settings, target_id: str | None) -> list:
    """Load configured targets, optionally narrowing to ONE by ``target_id`` (for a single-target
    smoke test). Raises ``ValueError`` with a clear, non-secret message on an unknown target id."""
    targets = load_targets(settings.targets_config_path)
    if target_id is None:
        return targets
    chosen = [t for t in targets if t.target_id == target_id]
    if not chosen:
        known = ", ".join(t.target_id for t in targets)
        raise ValueError(f"unknown --target {target_id!r}; configured targets are: {known}")
    return chosen


def build_context(
    settings: Settings,
    store: SqliteStore,
    *,
    mock: bool,
    question_filter: QuestionFilter | None = None,
    target_id: str | None = None,
    limit: int | None = None,
) -> OrchestratorContext:
    """Assemble an :class:`OrchestratorContext` from config (targets, prices, thresholds, budget).

    The model id, targets, prices, alert thresholds, and token budget all come from ``settings``.
    ``target_id`` narrows the run to a single target and ``limit`` caps the number of questions —
    both for one-target / one-question smoke tests; unset means the full configured fan-out.
    """
    if not mock:
        # Bridge .env-loaded credentials into os.environ so the provider SDKs (which read env vars,
        # not the Settings object) authenticate. Without this a .env-only setup passes preflight but
        # every live call fails with no key. No-op in mock mode (offline, no keys needed).
        apply_credentials_to_environment(settings)
    return OrchestratorContext(
        store=store,
        targets=_select_targets(settings, target_id),
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
        limit=limit,
    )


def check_targets(settings: Settings, *, mock: bool) -> list[tuple[str, HealthResult]]:
    """Probe each configured target's health (no store, no writes).

    INACTIVE targets (e.g. Open Evidence, with no API access) are SKIPPED — reported distinctly,
    never probed, and never reported "live". Only ACTIVE targets get a real round-trip. For live
    probes the ``.env`` credentials are bridged into the environment first, exactly as a run does,
    so the SDKs authenticate (otherwise a valid ``.env``-only setup would falsely report FAIL).
    """
    if not mock:
        apply_credentials_to_environment(settings)
    results: list[tuple[str, HealthResult]] = []
    for t in load_targets(settings.targets_config_path):
        if not t.active:
            results.append(
                (
                    t.target_id,
                    HealthResult(
                        reachable=False,
                        skipped=True,
                        detail=f"{t.llm_name}: INACTIVE — skipped (not probed; no API access)",
                    ),
                )
            )
            continue
        results.append((t.target_id, build_adapter(t, mock=mock).health()))
    return results


def preflight_or_error(settings: Settings) -> str | None:
    """Startup credential preflight (FR-032; Principle VI) for live runs.

    Returns a clear, NON-SECRET error string when any required credential is missing (so the
    caller can submit nothing and exit non-zero), or ``None`` when all are present. On success the
    resolved secrets are registered with the logger so they are masked everywhere (never logged).
    The web ``/health`` endpoint exposes the same presence gate (shared ``credential_preflight``).
    """
    missing = credential_preflight(settings)
    if missing:
        return (
            "preflight failed: missing required credential(s): "
            + ", ".join(missing)
            + " — set them in .env or the environment. Nothing was submitted."
        )
    for field_name in ("anthropic_api_key", "openai_api_key", "google_api_key"):
        secret = getattr(settings, field_name)
        if secret is not None:
            register_secret(secret.get_secret_value())  # mask it in every log sink
    return None


# --------------------------------------------------------------------------- #
# Commands (return values for testability; printing is a side effect)
# --------------------------------------------------------------------------- #
def cmd_run(
    settings: Settings,
    store: SqliteStore,
    *,
    mock: bool,
    question_filter: QuestionFilter | None = None,
    target_id: str | None = None,
    limit: int | None = None,
) -> RunSummary:
    """Execute a run (optionally a single target / limited subset) and return its summary.

    When ``target_id`` or ``limit`` is set (a smoke test), prints a per-response capture + scoring
    confirmation so you can verify ONE target end-to-end: a real 200 → SUCCESS, and that a
    ScoringRecord was written for it.
    """
    ctx = build_context(
        settings,
        store,
        mock=mock,
        question_filter=question_filter,
        target_id=target_id,
        limit=limit,
    )
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
    if target_id is not None or limit is not None:
        _print_capture_scoring_confirmation(store, state)
    return summary


def _print_capture_scoring_confirmation(store: SqliteStore, state: RunState) -> None:
    """Per-response capture + scoring confirmation for a smoke test (FR-015): for each response in
    the run, show status and whether a versioned ScoringRecord exists (with a one-line summary).
    FAILED/BLOCKED responses carry no text, so they are not scored — that is expected, not an error.
    """
    print("  capture + scoring (this run):")
    for r in state.responses:
        score = store.scores.latest_for(r.response_id)
        if score is not None:
            scored = (
                f"scored v{score.version} "
                f"sentiment={score.sentiment_score:+.2f} "
                f"position={score.competitive_position} citation={score.citation_status}"
            )
        else:
            scored = "not scored (no capturable text)"
        print(
            f"    [{r.status}] {r.question_id} · {_target_display(r.target_id)}"
            + (f" — {r.error_class}" if r.status is ResponseStatus.FAILED and r.error_class else "")
            + f"\n        {scored}"
        )


def cmd_health_check(settings: Settings, *, mock: bool) -> bool:
    """Probe every ACTIVE target with a real round-trip; return True iff all ACTIVE ones reach.

    Three states are reported: ``OK`` (round-trip succeeded), ``FAIL`` (probed but unreachable),
    and ``SKIP`` (inactive — deliberately not probed). The all-OK verdict considers only probed
    (active) targets, so a skipped inactive target neither passes nor fails the check.
    """
    results = check_targets(settings, mock=mock)
    probed = [(tid, h) for tid, h in results if not h.skipped]
    all_ok = all(h.reachable for _, h in probed)
    for target_id, health in results:
        tag = "SKIP" if health.skipped else ("OK  " if health.reachable else "FAIL")
        print(f"[{tag}] {target_id}: {health.detail}")
    print(
        "health-check: "
        + ("all ACTIVE targets reachable" if all_ok else "one or more ACTIVE targets UNREACHABLE")
    )
    return all_ok


def cmd_dry_run(settings: Settings, *, mock: bool) -> bool:
    """Validate config + connectivity without writing anything; return True iff valid."""
    targets = load_targets(settings.targets_config_path)  # parses/validates the targets config
    print(f"config OK: {len(targets)} target(s) loaded from {settings.targets_config_path}")
    ok = cmd_health_check(settings, mock=mock)
    print("dry-run: validated, wrote nothing")
    return ok


def cmd_import_questions(
    store: SqliteStore, file_path: str, *, dry_run: bool = False
) -> ImportReport:
    """Import a curated question bank as PENDING (idempotent upsert by id). Returns the report."""
    report = import_questions(store.questions, file_path, dry_run=dry_run)
    verb = "would import" if dry_run else "imported"
    print(
        f"{verb} {report.processed} question(s) from {file_path}: "
        f"created={report.created} updated={report.updated} skipped={report.skipped} "
        f"(all PENDING — approve before any run)"
    )
    return report


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


def cmd_approve_all_test_numbered(
    store: SqliteStore,
) -> tuple[int, list[tuple[str, str | None, str | None]], list[tuple[str, str | None, str | None]]]:
    """TEST helper (NOT the formal MA sign-off): approve every active question with a numbered
    approver + note, idempotently.

    Active questions are processed in stable ``question_id`` order; the Nth (1-based) gets
    ``approver_name='approver-N'`` and ``approval_note='test-N'``. Idempotent — a question already
    in its target state is skipped (no new version, no audit). Re-running reassigns the same N to
    the same ``question_id``.

    This goes through the repository ``set_approval`` seam (the same persistence the approval gate
    delegates to) plus the audit log — never raw SQL — because the formal gate is forward-only
    (PENDING→APPROVED→REJECTED) and so cannot re-stamp an already-APPROVED question's approver.
    Returns ``(approved_active_count, first_three, last_three)`` for confirmation.
    """
    svc = QuestionService(store.questions)
    active = sorted(svc.list_questions(active=True), key=lambda q: q.question_id)
    for n, q in enumerate(active, start=1):
        approver, note = f"approver-{n}", f"test-{n}"
        if (
            q.approval_status is ApprovalStatus.APPROVED
            and q.approver_name == approver
            and q.approval_note == note
        ):
            continue  # already in target state — idempotent no-op (no duplicate version)
        store.questions.set_approval(q.question_id, ApprovalStatus.APPROVED, approver, note=note)
        store.audit.append(
            approval_audit_event(
                event_type=AuditEventType.QUESTION_APPROVED,
                question_id=q.question_id,
                approver=approver,
                reason=note,
            )
        )

    approved = sorted(store.questions.approved_active(), key=lambda q: q.question_id)
    rows = [(q.question_id, q.approver_name, q.approval_note) for q in approved]
    first_three, last_three = rows[:3], rows[-3:]
    print(f"approve-all-test-numbered: {len(approved)} APPROVED + active question(s)")
    for label, subset in (("first 3", first_three), ("last 3", last_three)):
        print(f"  {label}:")
        for qid, name, note in subset:
            print(f"    {qid}  approver_name={name}  note={note}")
    return len(approved), first_three, last_three


def cmd_reset_to_pending(store: SqliteStore) -> int:
    """Companion to ``approve-all-test-numbered``: reset EVERY question back to PENDING and clear
    its ``approver_name`` and ``approval_note`` (so the real demo starts from a clean slate before
    the Medical Affairs approver signs off on the live subset).

    Idempotent — a question already PENDING with no approver/note is skipped. Uses the same
    ``set_approval`` seam + audit log; the reset is recorded as a QUESTION_EDITED curation event.
    Returns the number of questions actually changed.
    """
    svc = QuestionService(store.questions)
    changed = 0
    for q in sorted(svc.list_questions(), key=lambda q: q.question_id):
        if (
            q.approval_status is ApprovalStatus.PENDING
            and q.approver_name is None
            and q.approval_note is None
        ):
            continue  # already clean — idempotent no-op
        store.questions.set_approval(q.question_id, ApprovalStatus.PENDING, None, note=None)
        store.audit.append(
            approval_audit_event(
                event_type=AuditEventType.QUESTION_EDITED,
                question_id=q.question_id,
                approver="test-harness",
                reason="reset to PENDING; cleared approver_name and note",
            )
        )
        changed += 1

    pending = svc.list_questions(approval_status=ApprovalStatus.PENDING)
    approved_active = len(store.questions.approved_active())
    print(
        f"reset-to-pending: {changed} changed; now {len(pending)} PENDING, "
        f"{approved_active} APPROVED + active"
    )
    return changed


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
    if s.failures_by_error_class:
        lines.append(f"  failures by class   : {s.failures_by_error_class}")
    if s.budget_exhausted:
        lines.append("  ** PAUSED: token budget reached — rerun to resume the remaining bank **")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
def _add_target_limit_args(p: argparse.ArgumentParser) -> None:
    """Single-target / limited-run flags shared by ``run`` and ``subset`` (smoke-test one provider).

    ``--target`` restricts the run to one configured target id; ``--limit`` caps the number of
    approved questions dispatched (e.g. ``--limit 1`` for a one-call end-to-end check).
    """
    p.add_argument("--target", help="restrict the run to ONE configured target id (smoke test)")
    p.add_argument(
        "--limit", type=int, help="cap the number of approved questions dispatched (e.g. 1)"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evidence-monitor", description="Evidence Monitoring Agent"
    )
    parser.add_argument(
        "--mock", action="store_true", help="run offline with deterministic adapters"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run the approved question bank (capture → score → alert)")
    _add_target_limit_args(run_p)
    sub.add_parser("dry-run", help="validate config + connectivity; write nothing")
    sub.add_parser("health-check", help="real round-trip per ACTIVE target (inactive are skipped)")

    importer = sub.add_parser(
        "import-questions", help="import a curated question bank (CSV/Excel) as PENDING"
    )
    importer.add_argument("--file", required=True, help="path to the question-bank CSV/Excel file")
    importer.add_argument(
        "--dry-run", action="store_true", help="report what would import without writing"
    )

    subset = sub.add_parser("subset", help="run a subset of approved questions")
    subset.add_argument("--persona", choices=[p.value for p in Persona])
    subset.add_argument("--therapeutic-area")
    subset.add_argument("--domain", choices=[d.value for d in Domain])
    _add_target_limit_args(subset)

    sub.add_parser(
        "approve-all-test-numbered",
        help="TEST: approve all active questions with numbered approver/note (NOT MA sign-off)",
    )
    sub.add_parser(
        "reset-to-pending",
        help="reset ALL questions to PENDING and clear approver_name/note (pre-demo reset)",
    )

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
        # Live runs preflight credentials BEFORE touching the store or any target (FR-032). Mock
        # runs are fully offline (no keys), so the gate is skipped.
        if not mock:
            error = preflight_or_error(settings)
            if error is not None:
                print(f"error: {error}", file=sys.stderr)
                return 1
        store = SqliteStore(settings.db_path)
        try:
            question_filter = _subset_filter(args) if args.command == "subset" else None
            cmd_run(
                settings,
                store,
                mock=mock,
                question_filter=question_filter,
                target_id=args.target,
                limit=args.limit,
            )
        except ValueError as exc:  # e.g. unknown --target
            print(f"error: {exc}", file=sys.stderr)
            return 1
        finally:
            store.close()
        return 0

    if args.command == "import-questions":
        store = SqliteStore(settings.db_path)
        try:
            cmd_import_questions(store, args.file, dry_run=args.dry_run)
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        finally:
            store.close()
        return 0

    if args.command in ("approve-all-test-numbered", "reset-to-pending"):
        store = SqliteStore(settings.db_path)
        try:
            if args.command == "approve-all-test-numbered":
                cmd_approve_all_test_numbered(store)
            else:
                cmd_reset_to_pending(store)
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
    "cmd_approve_all_test_numbered",
    "cmd_dry_run",
    "cmd_health_check",
    "cmd_import_questions",
    "cmd_reject",
    "cmd_reset_to_pending",
    "cmd_run",
    "main",
    "preflight_or_error",
]
