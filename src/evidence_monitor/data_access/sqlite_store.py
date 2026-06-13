"""SQLite implementation of the data-access seam (Principle X).

This is the local POC binding for the protocols in ``interface.py``. It owns schema creation and
a single ``sqlite3`` connection shared with the audit writer, and implements every repository so
the :class:`~evidence_monitor.data_access.interface.DataAccess` facade is satisfiable from one
object. Production swaps this file for Aurora/DynamoDB behind the same protocols — core logic is
unchanged (DuckDB analytic reads remain an optional, additive read path, not wired here).

Guarantees enforced here, not just described:
- **Immutable responses** — :meth:`_ResponseRepo.insert` refuses to overwrite an existing id.
- **Versioned questions / scores** — edits and re-scores append a new version; history is kept.
- **Soft-delete** — deactivation flips ``active`` with a reason; rows are never physically purged.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from evidence_monitor.data_access.audit import SqliteAuditWriter
from evidence_monitor.data_access.interface import Page, QueryFilters, RunTotals
from evidence_monitor.data_access.models import (
    ALERT_SEVERITY,
    Alert,
    AlertRule,
    ApprovalStatus,
    CitationStatus,
    CompetitivePosition,
    Domain,
    Persona,
    Question,
    Run,
    ScoringRecord,
    TriggerType,
)
from evidence_monitor.data_access.queries import query_responses, row_to_response
from evidence_monitor.response_repo.schema import Response

_SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    question_id     TEXT NOT NULL,
    version         INTEGER NOT NULL,
    question_text   TEXT NOT NULL,
    persona         TEXT NOT NULL,
    therapeutic_area TEXT NOT NULL,
    brand_focus     TEXT NOT NULL,
    domain          TEXT NOT NULL,
    active          INTEGER NOT NULL,
    approval_status TEXT NOT NULL,
    approver_name   TEXT,
    deactivated_reason TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (question_id, version)
);

CREATE TABLE IF NOT EXISTS responses (
    response_id        TEXT PRIMARY KEY,
    run_id             TEXT NOT NULL,
    question_id        TEXT NOT NULL,
    target_id          TEXT NOT NULL,
    timestamp_utc      TEXT NOT NULL,
    llm_name           TEXT NOT NULL,
    llm_model_version  TEXT NOT NULL,
    persona            TEXT NOT NULL,
    therapeutic_area   TEXT NOT NULL,
    brand_focus        TEXT NOT NULL,
    domain             TEXT NOT NULL,
    response_text      TEXT NOT NULL,
    response_tokens    INTEGER NOT NULL,
    finish_reason      TEXT NOT NULL,
    status             TEXT NOT NULL,
    block_reason       TEXT,
    alert_triggered    INTEGER NOT NULL,
    created_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id                      TEXT PRIMARY KEY,
    trigger_type                TEXT NOT NULL,
    started_at                  TEXT NOT NULL,
    ended_at                    TEXT,
    questions_attempted         INTEGER NOT NULL,
    responses_captured          INTEGER NOT NULL,
    failure_count               INTEGER NOT NULL,
    total_tokens                INTEGER NOT NULL,
    est_cost                    REAL NOT NULL,
    last_completed_question_id  TEXT
);

CREATE TABLE IF NOT EXISTS scoring_records (
    score_id            TEXT PRIMARY KEY,
    response_id         TEXT NOT NULL,
    version             INTEGER NOT NULL,
    sentiment_score     REAL NOT NULL,
    competitive_position TEXT NOT NULL,
    citation_status     TEXT NOT NULL,
    brand_mentions      TEXT NOT NULL,
    competitor_sentiments TEXT NOT NULL,
    key_claims          TEXT NOT NULL,
    scoring_rationale   TEXT NOT NULL,
    scorer_model        TEXT NOT NULL,
    is_human_override   INTEGER NOT NULL,
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id     TEXT PRIMARY KEY,
    score_id     TEXT NOT NULL,
    response_id  TEXT NOT NULL,
    rule_fired   TEXT NOT NULL,
    severity     INTEGER NOT NULL,
    reason       TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id     TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    role         TEXT NOT NULL,
    target       TEXT NOT NULL,
    ts           TEXT NOT NULL,
    http_status  INTEGER,
    detail       TEXT NOT NULL
);
"""


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------- #
# Repositories
# --------------------------------------------------------------------------- #
class _QuestionRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _max_version(self, question_id: str) -> int | None:
        row = self._conn.execute(
            "SELECT MAX(version) FROM questions WHERE question_id = ?", (question_id,)
        ).fetchone()
        return row[0] if row and row[0] is not None else None

    def upsert(self, q: Question) -> Question:
        """Insert a new question, or append the next version on edit (history retained)."""
        latest = self._max_version(q.question_id)
        version = 1 if latest is None else latest + 1
        stored = q.model_copy(update={"version": version, "updated_at": datetime.now(UTC)})
        self._insert_version(stored)
        return stored

    def _insert_version(self, q: Question, *, deactivated_reason: str | None = None) -> None:
        self._conn.execute(
            """
            INSERT INTO questions
                (question_id, version, question_text, persona, therapeutic_area, brand_focus,
                 domain, active, approval_status, approver_name, deactivated_reason,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                q.question_id,
                q.version,
                q.question_text,
                str(q.persona),
                q.therapeutic_area,
                q.brand_focus,
                str(q.domain),
                int(q.active),
                str(q.approval_status),
                q.approver_name,
                deactivated_reason,
                q.created_at.isoformat(),
                q.updated_at.isoformat(),
            ),
        )
        self._conn.commit()

    def set_approval(
        self,
        question_id: str,
        status: ApprovalStatus,
        approver: str,
        reason: str | None = None,
    ) -> Question:
        """Record an approval transition as a new version (no overwrite of history)."""
        current = self._latest(question_id)
        if current is None:
            raise KeyError(f"unknown question_id: {question_id}")
        version = (self._max_version(question_id) or 0) + 1
        updated = current.model_copy(
            update={
                "version": version,
                "approval_status": status,
                "approver_name": approver,
                "updated_at": datetime.now(UTC),
            }
        )
        self._insert_version(updated, deactivated_reason=reason)
        return updated

    def deactivate(self, question_id: str, reason: str) -> Question:
        """Soft-delete: append an inactive version with a reason. Never physically purged."""
        current = self._latest(question_id)
        if current is None:
            raise KeyError(f"unknown question_id: {question_id}")
        version = (self._max_version(question_id) or 0) + 1
        updated = current.model_copy(
            update={"version": version, "active": False, "updated_at": datetime.now(UTC)}
        )
        self._insert_version(updated, deactivated_reason=reason)
        return updated

    def get(self, question_id: str) -> Question | None:
        """The latest version of one question (public read-by-id)."""
        return self._latest(question_id)

    def _latest(self, question_id: str) -> Question | None:
        row = self._conn.execute(
            """
            SELECT * FROM questions WHERE question_id = ?
            ORDER BY version DESC LIMIT 1
            """,
            (question_id,),
        ).fetchone()
        return _row_to_question(row) if row else None

    def _latest_all(self) -> list[Question]:
        rows = self._conn.execute(
            """
            SELECT q.* FROM questions q
            JOIN (
                SELECT question_id, MAX(version) AS v FROM questions GROUP BY question_id
            ) m ON q.question_id = m.question_id AND q.version = m.v
            ORDER BY q.question_id
            """
        ).fetchall()
        return [_row_to_question(r) for r in rows]

    def list(
        self,
        *,
        approval_status: ApprovalStatus | None = None,
        active: bool | None = None,
        persona: Persona | None = None,
        therapeutic_area: str | None = None,
    ) -> list[Question]:
        out = self._latest_all()
        if approval_status is not None:
            out = [q for q in out if q.approval_status is approval_status]
        if active is not None:
            out = [q for q in out if q.active is active]
        if persona is not None:
            out = [q for q in out if q.persona is persona]
        if therapeutic_area is not None:
            out = [q for q in out if q.therapeutic_area == therapeutic_area]
        return out

    def approved_active(self) -> list[Question]:
        return [q for q in self._latest_all() if q.run_eligible]


class _ResponseRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, r: Response) -> Response:
        """Write-once. Raises if a response with this id already exists (Principle II)."""
        if self.get(r.response_id) is not None:
            raise ValueError(f"response {r.response_id} already exists; responses are immutable")
        self._conn.execute(
            """
            INSERT INTO responses
                (response_id, run_id, question_id, target_id, timestamp_utc, llm_name,
                 llm_model_version, persona, therapeutic_area, brand_focus, domain,
                 response_text, response_tokens, finish_reason, status, block_reason,
                 alert_triggered, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r.response_id,
                r.run_id,
                r.question_id,
                r.target_id,
                r.timestamp_utc.isoformat(),
                r.llm_name,
                r.llm_model_version,
                str(r.persona),
                r.therapeutic_area,
                r.brand_focus,
                str(r.domain),
                r.response_text,
                r.response_tokens,
                str(r.finish_reason),
                str(r.status),
                r.block_reason,
                int(r.alert_triggered),
                r.created_at.isoformat(),
            ),
        )
        self._conn.commit()
        return r

    def get(self, response_id: str) -> Response | None:
        row = self._conn.execute(
            "SELECT * FROM responses WHERE response_id = ?", (response_id,)
        ).fetchone()
        return row_to_response(row) if row else None

    def query(
        self, filters: QueryFilters, *, page: int = 1, page_size: int | None = 50
    ) -> Page[Response]:
        """Filtered/paginated reads across every query dimension (delegates to queries.py)."""
        return query_responses(self._conn, filters, page=page, page_size=page_size)


class _RunRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, trigger: TriggerType) -> Run:
        run = Run(trigger_type=trigger)
        self._conn.execute(
            """
            INSERT INTO runs
                (run_id, trigger_type, started_at, ended_at, questions_attempted,
                 responses_captured, failure_count, total_tokens, est_cost,
                 last_completed_question_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                str(run.trigger_type),
                run.started_at.isoformat(),
                None,
                run.questions_attempted,
                run.responses_captured,
                run.failure_count,
                run.total_tokens,
                run.est_cost,
                run.last_completed_question_id,
            ),
        )
        self._conn.commit()
        return run

    def checkpoint(self, run_id: str, last_completed_question_id: str) -> None:
        self._conn.execute(
            "UPDATE runs SET last_completed_question_id = ? WHERE run_id = ?",
            (last_completed_question_id, run_id),
        )
        self._conn.commit()

    def finalize(self, run_id: str, totals: RunTotals) -> Run:
        ended = (totals.ended_at or datetime.now(UTC)).isoformat()
        self._conn.execute(
            """
            UPDATE runs SET ended_at = ?, questions_attempted = ?, responses_captured = ?,
                failure_count = ?, total_tokens = ?, est_cost = ?
            WHERE run_id = ?
            """,
            (
                ended,
                totals.questions_attempted,
                totals.responses_captured,
                totals.failure_count,
                totals.total_tokens,
                totals.est_cost,
                run_id,
            ),
        )
        self._conn.commit()
        run = self.get(run_id)
        assert run is not None
        return run

    def get(self, run_id: str) -> Run | None:
        row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return _row_to_run(row) if row else None


class _ScoringRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add_version(self, s: ScoringRecord) -> ScoringRecord:
        """Append a new scoring version for the response (never mutates the response)."""
        row = self._conn.execute(
            "SELECT MAX(version) FROM scoring_records WHERE response_id = ?", (s.response_id,)
        ).fetchone()
        next_version = (row[0] or 0) + 1
        stored = s.model_copy(update={"version": next_version})
        self._conn.execute(
            """
            INSERT INTO scoring_records
                (score_id, response_id, version, sentiment_score, competitive_position,
                 citation_status, brand_mentions, competitor_sentiments, key_claims,
                 scoring_rationale, scorer_model, is_human_override, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stored.score_id,
                stored.response_id,
                stored.version,
                stored.sentiment_score,
                str(stored.competitive_position),
                str(stored.citation_status),
                json.dumps(stored.brand_mentions),
                json.dumps(stored.competitor_sentiments),
                json.dumps(stored.key_claims),
                stored.scoring_rationale,
                stored.scorer_model,
                int(stored.is_human_override),
                stored.created_at.isoformat(),
            ),
        )
        self._conn.commit()
        return stored

    def latest_for(self, response_id: str) -> ScoringRecord | None:
        row = self._conn.execute(
            """
            SELECT * FROM scoring_records WHERE response_id = ?
            ORDER BY version DESC LIMIT 1
            """,
            (response_id,),
        ).fetchone()
        return _row_to_scoring(row) if row else None

    def versions_for(self, response_id: str) -> list[ScoringRecord]:
        rows = self._conn.execute(
            "SELECT * FROM scoring_records WHERE response_id = ? ORDER BY version ASC",
            (response_id,),
        ).fetchall()
        return [_row_to_scoring(r) for r in rows]


class _AlertRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, a: Alert) -> Alert:
        self._conn.execute(
            """
            INSERT INTO alerts (alert_id, score_id, response_id, rule_fired, severity, reason,
                                created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                a.alert_id,
                a.score_id,
                a.response_id,
                str(a.rule_fired),
                a.severity,
                a.reason,
                a.created_at.isoformat(),
            ),
        )
        self._conn.commit()
        return a

    def list(self, *, order_by_severity: bool = True) -> list[Alert]:
        order = "severity DESC, created_at ASC" if order_by_severity else "created_at ASC"
        rows = self._conn.execute(f"SELECT * FROM alerts ORDER BY {order}").fetchall()
        return [_row_to_alert(r) for r in rows]


# --------------------------------------------------------------------------- #
# Row → model adapters
# --------------------------------------------------------------------------- #
def _row_to_question(r: sqlite3.Row) -> Question:
    return Question(
        question_id=r["question_id"],
        version=r["version"],
        question_text=r["question_text"],
        persona=Persona(r["persona"]),
        therapeutic_area=r["therapeutic_area"],
        brand_focus=r["brand_focus"],
        domain=Domain(r["domain"]),
        active=bool(r["active"]),
        approval_status=ApprovalStatus(r["approval_status"]),
        approver_name=r["approver_name"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


def _row_to_run(r: sqlite3.Row) -> Run:
    return Run(
        run_id=r["run_id"],
        trigger_type=TriggerType(r["trigger_type"]),
        started_at=r["started_at"],
        ended_at=r["ended_at"],
        questions_attempted=r["questions_attempted"],
        responses_captured=r["responses_captured"],
        failure_count=r["failure_count"],
        total_tokens=r["total_tokens"],
        est_cost=r["est_cost"],
        last_completed_question_id=r["last_completed_question_id"],
    )


def _row_to_scoring(r: sqlite3.Row) -> ScoringRecord:
    return ScoringRecord(
        score_id=r["score_id"],
        response_id=r["response_id"],
        version=r["version"],
        sentiment_score=r["sentiment_score"],
        competitive_position=CompetitivePosition(r["competitive_position"]),
        citation_status=CitationStatus(r["citation_status"]),
        brand_mentions=json.loads(r["brand_mentions"]),
        competitor_sentiments=json.loads(r["competitor_sentiments"]),
        key_claims=json.loads(r["key_claims"]),
        scoring_rationale=r["scoring_rationale"],
        scorer_model=r["scorer_model"],
        is_human_override=bool(r["is_human_override"]),
        created_at=r["created_at"],
    )


def _row_to_alert(r: sqlite3.Row) -> Alert:
    return Alert(
        alert_id=r["alert_id"],
        score_id=r["score_id"],
        response_id=r["response_id"],
        rule_fired=AlertRule(r["rule_fired"]),
        severity=r["severity"],
        reason=r["reason"],
        created_at=r["created_at"],
    )


# --------------------------------------------------------------------------- #
# Facade
# --------------------------------------------------------------------------- #
class SqliteStore:
    """Concrete :class:`~evidence_monitor.data_access.interface.DataAccess` over SQLite.

    Pass ``":memory:"`` for an ephemeral store (used by tests). The schema is created on
    construction; all repositories share one connection so writes are atomic across tables.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        # ``check_same_thread=False`` lets the FastAPI app (whose sync routes run in a worker
        # threadpool) share this connection. Access is sequential in the POC and SQLite serializes
        # statements, so this is safe; production swaps to Aurora/DynamoDB behind the seam anyway.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

        self.questions = _QuestionRepo(self._conn)
        self.responses = _ResponseRepo(self._conn)
        self.runs = _RunRepo(self._conn)
        self.scores = _ScoringRepo(self._conn)
        self.alerts = _AlertRepo(self._conn)
        self.audit = SqliteAuditWriter(self._conn)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()


# Keep the severity table importable from the store namespace for convenience.
__all__ = ["ALERT_SEVERITY", "SqliteStore"]
