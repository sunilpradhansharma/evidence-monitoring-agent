"""Scheduled, unattended runs (APScheduler / cron).

Fires the orchestrator on the cron from config (``EM_SCHEDULE_CRON``, default ``0 2 * * *`` —
daily at 02:00 UTC). Each fire is one orchestrator run: it gets a unique ``run_id`` (assigned by
the run manager) and produces a run summary — counts by status, alert count, total tokens, and
estimated cost — which is logged. The per-run token budget is enforced inside the orchestrator
(it pauses and notifies rather than overrun).

Maps to Amazon EventBridge Scheduler in production (Principle X) — a config/entry swap only.
"""

from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from evidence_monitor.cli import build_context
from evidence_monitor.config.settings import Settings, get_settings
from evidence_monitor.data_access.models import TriggerType
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.observability.logging import get_logger, log_event
from evidence_monitor.orchestrator import run as run_graph
from evidence_monitor.orchestrator.state import RunSummary

_LOGGER = get_logger("evidence_monitor.scheduler")
_JOB_ID = "daily-run"


def run_once(settings: Settings | None = None, *, mock: bool | None = None) -> RunSummary:
    """Execute one scheduled run and return (and log) its summary."""
    settings = settings or get_settings()
    use_mock = settings.offline_mock if mock is None else mock
    store = SqliteStore(settings.db_path)
    try:
        ctx = build_context(settings, store, mock=use_mock)
        summary = run_graph(ctx, trigger=TriggerType.SCHEDULED).summary
        log_event(
            _LOGGER,
            "INFO",
            "scheduled run complete",
            run_id=summary.run_id,
            responses_by_status=summary.responses_by_status,
            alerts=summary.alert_count,
            total_tokens=summary.total_tokens,
            est_cost=summary.est_cost,
            budget_exhausted=summary.budget_exhausted,
        )
        return summary
    finally:
        store.close()


def build_scheduler(
    settings: Settings | None = None, *, scheduler: BlockingScheduler | None = None
) -> BlockingScheduler:
    """Build a scheduler with the daily run wired to the cron from config (UTC)."""
    settings = settings or get_settings()
    scheduler = scheduler or BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run_once,
        trigger=CronTrigger.from_crontab(settings.schedule_cron, timezone="UTC"),
        id=_JOB_ID,
        replace_existing=True,
    )
    return scheduler


def main() -> None:  # pragma: no cover - blocking process entry point
    """Start the blocking scheduler (Ctrl-C to stop)."""
    scheduler = build_scheduler()
    log_event(_LOGGER, "INFO", "scheduler started", cron=get_settings().schedule_cron, tz="UTC")
    scheduler.start()


__all__ = ["build_scheduler", "main", "run_once"]
