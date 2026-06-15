"""Component tests for the scheduler: cron wiring from config + a unique-run-id summary."""

from __future__ import annotations

from pathlib import Path

from tests.fixtures import sample_questions

from evidence_monitor import scheduler
from evidence_monitor.config.settings import Settings
from evidence_monitor.data_access.models import ApprovalStatus
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.orchestrator.state import RunSummary

TARGETS_CFG = str(Path(__file__).resolve().parents[2] / "src/evidence_monitor/config/targets.yaml")


def _settings(**overrides) -> Settings:
    return Settings(EM_OFFLINE_MOCK=True, EM_TARGETS_CONFIG=TARGETS_CFG, **overrides)


def test_default_schedule_is_daily_0200_utc():
    job = scheduler.build_scheduler(_settings()).get_job("daily-run")
    trigger = str(job.trigger)
    assert "hour='2'" in trigger
    assert "minute='0'" in trigger


def test_schedule_cron_comes_from_config():
    job = scheduler.build_scheduler(_settings(EM_SCHEDULE_CRON="30 5 * * 1")).get_job("daily-run")
    trigger = str(job.trigger)
    assert "hour='5'" in trigger
    assert "minute='30'" in trigger
    assert "day_of_week='1'" in trigger


def test_run_once_assigns_run_id_and_returns_summary(tmp_path):
    # Seed a file-backed DB, then let run_once reopen it and execute one scheduled run.
    db = tmp_path / "evidence.db"
    settings = _settings(EM_DB_PATH=str(db))
    seed = SqliteStore(str(db))
    for q in sample_questions():
        seed.questions.upsert(q)
        seed.questions.set_approval(q.question_id, ApprovalStatus.APPROVED, "reviewer")
    seed.close()

    summary = scheduler.run_once(settings, mock=True)

    assert isinstance(summary, RunSummary)
    assert summary.run_id  # unique id assigned by the run manager
    # 10 = persona-aware fan-out (the PROVIDER question also reaches the active dev stand-in target,
    # on top of the 3 unconditional providers serving every persona).
    assert summary.responses_by_status == {"SUCCESS": 10}
    assert summary.total_tokens > 0
    assert summary.est_cost > 0
