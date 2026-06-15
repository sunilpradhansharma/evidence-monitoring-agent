"""FastAPI app — ONE local web app combining read-only **Reports** and read-write **Approvals**.

**Reports are read-only; the only writes are local Medical Affairs Approvals** (Principle I). No
endpoint here submits a question to any LLM or takes any outward action — submission happens only
inside scheduled / CLI-triggered runs over APPROVED questions. The app is local-only for the POC:
bind to ``127.0.0.1`` (see :func:`serve`), no auth/RBAC (out of scope). The approver TYPES their
name and it is recorded on every approval action and appended to the audit log (SE-002).

Layout:
- ``GET /`` — the tabbed UI (Reports tab + Approvals tab; Score-review scaffolded, OFF by default).
- ``GET /reports/*`` — read-only JSON for the response repository (FR-012/024/025/026).
- ``GET /health`` — startup credential preflight (FR-032).
- ``POST /approvals/*`` — the ONLY writes; each appends to the append-only audit log (Principle II).

The Reports tab and the self-contained static export (``dashboard.render``) share one render path,
so the served view and the shareable ``.html`` are always identical.

The data store and settings are dependency-injected: tests pass an in-memory :class:`SqliteStore`
and a :class:`Settings`; in production both are built lazily on first request, so importing this
module has no filesystem side effect.
"""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from evidence_monitor.config.settings import Settings, credential_preflight, get_settings
from evidence_monitor.dashboard.json_api import (
    dashboard_payload,
    questions_payload,
    report_payload,
    response_payload,
    runs_payload,
)
from evidence_monitor.dashboard.render import (
    build_approved_questions,
    build_report,
    latest_per_question,
    render_app,
)
from evidence_monitor.data_access.interface import DataAccess, QueryFilters
from evidence_monitor.data_access.models import (
    ApprovalStatus,
    AuditEventType,
    Domain,
    Persona,
    Question,
    ResponseStatus,
)
from evidence_monitor.data_access.queries import to_csv, to_json
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.llm.registry import load_targets
from evidence_monitor.question_repo.approval import ApprovalError, approval_audit_event
from evidence_monitor.question_repo.repository import QuestionService


# --------------------------------------------------------------------------- #
# Request bodies (validation rejects blank approver / reason before the service)
# --------------------------------------------------------------------------- #
def _require_nonblank(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class ApproveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approver_name: str = Field(min_length=1)

    _strip_approver = field_validator("approver_name")(_require_nonblank)


class RejectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approver_name: str = Field(min_length=1)
    reason: str = Field(min_length=1)

    _strip_approver = field_validator("approver_name")(_require_nonblank)
    _strip_reason = field_validator("reason")(_require_nonblank)


class EditBody(BaseModel):
    """Partial question fields; only the fields sent are changed (new version). Approval state is
    NOT editable here — it moves only through approve/reject."""

    model_config = ConfigDict(extra="forbid")
    question_text: str | None = None
    persona: Persona | None = None
    therapeutic_area: str | None = None
    brand_focus: str | None = None
    domain: Domain | None = None
    active: bool | None = None


# --------------------------------------------------------------------------- #
# Store / settings wiring (lazy in prod, injected in tests)
# --------------------------------------------------------------------------- #
def get_store(request: Request) -> DataAccess:
    """Resolve the request's data store, building one from settings on first use if unset."""
    store = request.app.state.store
    if store is None:
        store = SqliteStore(get_app_settings(request).db_path)
        request.app.state.store = store
    return store


def get_app_settings(request: Request) -> Settings:
    """Resolve the app's settings, loading from the environment on first use if unset."""
    settings = request.app.state.settings
    if settings is None:
        settings = get_settings()
        request.app.state.settings = settings
    return settings


StoreDep = Annotated[DataAccess, Depends(get_store)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


# --------------------------------------------------------------------------- #
# Filter parsing (shared by the Reports tab and the Reports JSON endpoints)
# --------------------------------------------------------------------------- #
def _parse_dt(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    """Parse an ISO date / datetime; a bare ``YYYY-MM-DD`` ``date_to`` covers the whole day."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if end_of_day and len(value) == 10:  # date-only → include the full day
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return dt


def _enum_or_none(enum_cls, value: str | None):
    """Coerce a query string to an enum member, ignoring blanks / unknown values."""
    if not value:
        return None
    try:
        return enum_cls(value)
    except ValueError:
        return None


def _filters_from_params(params) -> QueryFilters:
    """Build a :class:`QueryFilters` from request query params (unset/blank ⇒ no constraint)."""
    return QueryFilters(
        run_id=params.get("run_id") or None,
        llm=params.get("llm") or None,
        persona=_enum_or_none(Persona, params.get("persona")),
        therapeutic_area=params.get("therapeutic_area") or None,
        brand=params.get("brand") or None,
        domain=params.get("domain") or None,
        status=_enum_or_none(ResponseStatus, params.get("status")),
        date_from=_parse_dt(params.get("date_from")),
        date_to=_parse_dt(params.get("date_to"), end_of_day=True),
        sentiment_min=_as_float(params.get("sentiment_min")),
        sentiment_max=_as_float(params.get("sentiment_max")),
        alert_status=_as_bool(params.get("alert_status")),
    )


def _as_float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _as_bool(value: str | None) -> bool | None:
    if value in (None, ""):
        return None
    return value.lower() in ("1", "true", "yes", "on")


# Dashboard period presets → a lookback window. "all"/unrecognized means no date bound.
_PERIOD_DAYS = {"7d": 7, "30d": 30}


def _period_date_from(period: str | None, *, now: datetime | None = None) -> datetime | None:
    """Translate a period preset (``7d`` / ``30d`` / ``all``) into a ``date_from`` cutoff."""
    days = _PERIOD_DAYS.get((period or "all").lower())
    if days is None:
        return None
    return (now or datetime.now(UTC)) - timedelta(days=days)


def _llms_from_params(params) -> set[str] | None:
    """Multi-select LLM filter (repeated ``llm=`` and/or comma-separated); None if empty."""
    values: list[str] = []
    for raw in params.getlist("llm"):
        values.extend(part.strip() for part in raw.split(",") if part.strip())
    return set(values) or None


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #
def create_app(store: DataAccess | None = None, settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. Pass ``store``/``settings`` to inject them (tests); else lazy."""
    app = FastAPI(title="Evidence Monitoring AI Agent")
    app.state.store = store
    app.state.settings = settings
    _register_ui(app)
    _register_reports(app)
    _register_health(app)
    _register_approvals(app)
    _register_score_review(app)
    _register_api(app)
    _register_spa(app)  # MUST be last: mounts assets + the SPA catch-all fallback.
    return app


# --------------------------------------------------------------------------- #
# Legacy server-rendered UI — kept reachable at /html during the React transition.
# The React SPA is now the PRIMARY UI at "/" (see _register_spa); this Jinja UI is unchanged
# and shares the same read-only render path + the same approve/reject write endpoints.
# --------------------------------------------------------------------------- #
def _build_index_html(request: Request, store: DataAccess, settings: Settings) -> str:
    """Render the legacy tabbed HTML app (Reports + Approvals). Read-only render path."""
    active_tab = request.query_params.get("tab", "reports")
    params = request.query_params

    # Reports default to the LATEST run when none is chosen (US5); an explicit run_id (or "All
    # runs" → no run_id, never reaches here because the empty value is falsy) overrides it.
    filters = _filters_from_params(params)
    if filters.run_id is None and "run_id" not in params:
        runs = store.runs.list()
        if runs:
            filters = replace(filters, run_id=runs[0].run_id)
    report = build_report(store, filters)

    # Approvals tab inputs. All reads are version-aware (latest version per question); the ONLY
    # writes remain the approve/reject endpoints. Status + persona filter the queue/lists.
    status_filter = (params.get("status") or "PENDING").upper()
    if status_filter not in {"PENDING", "APPROVED", "REJECTED", "ALL"}:
        status_filter = "PENDING"
    persona_filter = params.get("persona") or ""
    persona_enum = _enum_or_none(Persona, persona_filter)
    svc = QuestionService(store.questions)
    # latest_per_question guarantees one row per question at its current version (no version
    # leak); pending is persona-then-id sorted so the template can group it by persona.
    pending = latest_per_question(
        svc.list_questions(
            approval_status=ApprovalStatus.PENDING, active=True, persona=persona_enum
        )
    )
    pending.sort(key=lambda q: (str(q.persona), q.question_id))
    rejected = latest_per_question(
        svc.list_questions(approval_status=ApprovalStatus.REJECTED, persona=persona_enum)
    )
    rejected.sort(key=lambda q: q.question_id)
    # Read-only approved-questions view (Approvals tab) — through the question-repo read path.
    approved_view = build_approved_questions(
        store,
        persona=params.get("persona") or None,
        therapeutic_area=params.get("therapeutic_area") or None,
        domain=params.get("domain") or None,
        search=params.get("search") or None,
    )
    return render_app(
        report,
        pending_questions=pending,
        approved_view=approved_view,
        rejected_questions=rejected,
        status_filter=status_filter,
        persona_filter=persona_filter,
        active_tab=active_tab,
        score_review_enabled=settings.enable_score_review,
    )


def _register_ui(app: FastAPI) -> None:
    @app.get("/html", response_class=HTMLResponse)
    def index_html(request: Request, store: StoreDep, settings: SettingsDep) -> HTMLResponse:
        """Legacy server-rendered UI (kept working during the React transition)."""
        return HTMLResponse(_build_index_html(request, store, settings))


# --------------------------------------------------------------------------- #
# Reports (read-only)
# --------------------------------------------------------------------------- #
def _score_summary(store: DataAccess, response_id: str) -> dict | None:
    score = store.scores.latest_for(response_id)
    return score.model_dump(mode="json") if score else None


def _register_reports(app: FastAPI) -> None:
    @app.get("/reports/responses")
    def list_responses(request: Request, store: StoreDep, page: int = 1, page_size: int = 50):
        """Filtered, paginated responses + the latest score summary + alert flag (FR-012)."""
        filters = _filters_from_params(request.query_params)
        result = store.responses.query(filters, page=page, page_size=page_size)
        items = [
            {**r.model_dump(mode="json"), "latest_score": _score_summary(store, r.response_id)}
            for r in result.items
        ]
        return {
            "items": items,
            "page": result.page,
            "page_size": result.page_size,
            "total": result.total,
        }

    @app.get("/reports/responses/{response_id}")
    def get_response(response_id: str, store: StoreDep):
        """Full response text + all scoring versions + alerts (dashboard drill-down, FR-024)."""
        response = store.responses.get(response_id)
        if response is None:
            raise HTTPException(status_code=404, detail=f"unknown response_id: {response_id}")
        versions = store.scores.versions_for(response_id)
        alerts = [a for a in store.alerts.list() if a.response_id == response_id]
        return {
            "response": response.model_dump(mode="json"),
            "scoring_versions": [s.model_dump(mode="json") for s in versions],
            "alerts": [a.model_dump(mode="json") for a in alerts],
        }

    @app.get("/reports/alerts")
    def list_alerts(store: StoreDep):
        """Alerts ordered by severity (WRONG_INDICATION first)."""
        return [a.model_dump(mode="json") for a in store.alerts.list(order_by_severity=True)]

    @app.get("/reports/export")
    def export(request: Request, store: StoreDep, format: str = "csv") -> Response:
        """Export the current filter set to CSV or JSON (FR-025) — matches the on-screen view."""
        if format not in ("csv", "json"):
            raise HTTPException(status_code=400, detail="format must be 'csv' or 'json'")
        filters = _filters_from_params(request.query_params)
        rows = store.responses.query(filters, page_size=None).items
        if format == "json":
            return PlainTextResponse(to_json(rows), media_type="application/json")
        return PlainTextResponse(to_csv(rows), media_type="text/csv")

    @app.get("/reports/runs/{run_id}/summary")
    def run_summary(run_id: str, store: StoreDep):
        """Run summary (FR-026): timings, captured-by-status, alert count, tokens, cost."""
        run = store.runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"unknown run_id: {run_id}")
        rows = store.responses.query(QueryFilters(run_id=run_id), page_size=None).items
        by_status: dict[str, int] = {}
        for r in rows:
            by_status[str(r.status)] = by_status.get(str(r.status), 0) + 1
        run_response_ids = {r.response_id for r in rows}
        alert_count = sum(1 for a in store.alerts.list() if a.response_id in run_response_ids)
        return {
            "run_id": run.run_id,
            "trigger_type": str(run.trigger_type),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "ended_at": run.ended_at.isoformat() if run.ended_at else None,
            "questions_attempted": run.questions_attempted,
            "responses_by_status": by_status,
            "responses_captured": run.responses_captured,
            "failure_count": run.failure_count,
            "alert_count": alert_count,
            "total_tokens": run.total_tokens,
            "est_cost": run.est_cost,
        }


# --------------------------------------------------------------------------- #
# Health (startup credential preflight, FR-032)
# --------------------------------------------------------------------------- #
def _register_health(app: FastAPI) -> None:
    @app.get("/health")
    def health(settings: SettingsDep) -> JSONResponse:
        """Report whether required credentials are present (presence-only; no secret is read)."""
        missing = credential_preflight(settings)
        if missing:
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "missing": missing, "unreachable": []},
            )
        return JSONResponse(status_code=200, content={"status": "ok"})


# --------------------------------------------------------------------------- #
# Approvals (read-write, local Medical Affairs — the ONLY writes; each is audited)
# --------------------------------------------------------------------------- #
def _register_approvals(app: FastAPI) -> None:
    @app.get("/approvals/questions")
    def list_questions(
        store: StoreDep,
        status: ApprovalStatus | None = None,
        persona: Persona | None = None,
        therapeutic_area: str | None = None,
    ) -> list[Question]:
        """List the latest version of each question, optionally filtered (read-only)."""
        return QuestionService(store.questions).list_questions(
            approval_status=status, persona=persona, therapeutic_area=therapeutic_area
        )

    @app.post("/approvals/questions/{question_id}/approve")
    def approve_question(question_id: str, body: ApproveBody, store: StoreDep) -> Question:
        """Approve a question; records the approver + an audit entry. 404 unknown; 409 REJECTED."""
        svc = QuestionService(store.questions)
        try:
            question = svc.approve(question_id, body.approver_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ApprovalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        store.audit.append(
            approval_audit_event(
                event_type=AuditEventType.QUESTION_APPROVED,
                question_id=question_id,
                approver=body.approver_name,
            )
        )
        return question

    @app.post("/approvals/questions/{question_id}/reject")
    def reject_question(question_id: str, body: RejectBody, store: StoreDep) -> Question:
        """Reject a question (excluded from all runs), recording approver + reason + audit. 404."""
        svc = QuestionService(store.questions)
        try:
            question = svc.reject(question_id, body.approver_name, body.reason)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ApprovalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        store.audit.append(
            approval_audit_event(
                event_type=AuditEventType.QUESTION_REJECTED,
                question_id=question_id,
                approver=body.approver_name,
                reason=body.reason,
            )
        )
        return question

    @app.post("/approvals/questions/{question_id}/edit")
    def edit_question(question_id: str, body: EditBody, store: StoreDep) -> Question:
        """Edit a question — creates a NEW version (no hard delete, FR-001) + an audit entry."""
        changes = body.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            raise HTTPException(status_code=400, detail="no editable fields provided")
        svc = QuestionService(store.questions)
        try:
            question = svc.edit(question_id, **changes)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        store.audit.append(
            approval_audit_event(
                event_type=AuditEventType.QUESTION_EDITED,
                question_id=question_id,
                approver="curation",
                reason="fields: " + ", ".join(sorted(changes)),
            )
        )
        return question


# --------------------------------------------------------------------------- #
# Score review (FR-408) — scaffolded but OFF by default for the POC.
# --------------------------------------------------------------------------- #
def _register_score_review(app: FastAPI) -> None:
    @app.post("/score-review/{response_id}")
    def override_score(response_id: str, settings: SettingsDep) -> Response:
        """Human override of an AI score → a NEW versioned scoring record (the AI score is kept).

        Disabled in this build (``enable_score_review=False``); the route exists so the contract
        and the UI tab are wired, but it returns 404 until the feature is turned on.
        """
        if not settings.enable_score_review:
            raise HTTPException(status_code=404, detail="score review is disabled in this build")
        raise HTTPException(status_code=501, detail="score override not yet implemented")


# --------------------------------------------------------------------------- #
# Read-only JSON API (Part A) — powers the React dashboard. Reuses render.py via json_api;
# NO new aggregation and NO new write path (writes stay on /approvals/*).
# --------------------------------------------------------------------------- #
def _register_api(app: FastAPI) -> None:
    @app.get("/api/runs")
    def api_runs(store: StoreDep):
        """Runs for the run selector (most-recent first)."""
        return runs_payload(store)

    @app.get("/api/runs/{run_id}/report")
    def api_run_report(run_id: str, store: StoreDep):
        """Full Reports payload for one run (same aggregation as the HTML Reports view)."""
        try:
            return report_payload(store, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown run_id: {run_id}") from exc

    @app.get("/api/dashboard")
    def api_dashboard(request: Request, store: StoreDep, settings: SettingsDep):
        """Dashboard aggregate honoring the filter bar (persona / LLM multi-select / therapy /
        period) plus the ``include_dev`` toggle. Read-only; reuses ``build_dashboard``.

        The PROVIDER-only dev stand-in is excluded by default (``include_dev`` falsey) so the three
        general LLMs are the clean comparison; pass ``include_dev=true`` to fold it in. Per-target
        classification is always returned so the UI can render the toggle and distinguish targets.
        """
        params = request.query_params
        filters = QueryFilters(
            persona=_enum_or_none(Persona, params.get("persona")),
            therapeutic_area=params.get("therapeutic_area") or None,
            date_from=_period_date_from(params.get("period")),
        )
        try:
            targets = load_targets(settings.targets_config_path)
        except (OSError, ValueError):
            targets = None  # classification falls back to "full LLM"; dashboard still renders
        return dashboard_payload(
            store,
            filters=filters,
            llms=_llms_from_params(params),
            include_dev=bool(_as_bool(params.get("include_dev"))),
            targets=targets,
        )

    @app.get("/api/questions")
    def api_questions(store: StoreDep, status: str | None = None, persona: str | None = None):
        """Version-aware questions for the Approvals tab + global status counts (read-only)."""
        return questions_payload(store, status=status, persona=persona)

    @app.get("/api/responses/{response_id}")
    def api_response(response_id: str, store: StoreDep):
        """Full response text + scoring rationale for coverage-cell / alert click-through."""
        try:
            return response_payload(store, response_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail=f"unknown response_id: {response_id}"
            ) from exc


# --------------------------------------------------------------------------- #
# React SPA serving — built Vite assets at "/", with a client-side-routing fallback.
# Registered LAST so every explicit API/HTML route wins; only unknown GET paths fall through to
# index.html. When the build is absent (tests / fresh checkout) "/" serves the legacy HTML so the
# app still works without a frontend build.
# --------------------------------------------------------------------------- #
def _frontend_dist() -> Path:
    """Resolve the built-frontend directory (override with ``EM_FRONTEND_DIST``)."""
    override = os.environ.get("EM_FRONTEND_DIST")
    if override:
        return Path(override)
    # api.py → src/evidence_monitor/ → src/ → repo root → frontend/dist
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _register_spa(app: FastAPI) -> None:
    dist = _frontend_dist()
    index_file = dist / "index.html"
    assets_dir = dist / "assets"

    if index_file.exists():
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/", include_in_schema=False)
        def spa_root() -> FileResponse:
            return FileResponse(str(index_file))

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str) -> Response:
            """Serve index.html for client-side routes; never shadow API/HTML/health paths."""
            reserved = ("api/", "reports/", "approvals/", "assets/", "score-review/")
            if full_path == "html" or full_path.startswith(reserved) or full_path == "health":
                raise HTTPException(status_code=404, detail="not found")
            candidate = dist / full_path
            if candidate.is_file():  # static root files (favicon, etc.)
                return FileResponse(str(candidate))
            return FileResponse(str(index_file))
    else:
        # No build present → "/" serves the legacy HTML so the app works without a frontend build.
        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        def root_html(request: Request, store: StoreDep, settings: SettingsDep) -> HTMLResponse:
            return HTMLResponse(_build_index_html(request, store, settings))


# --------------------------------------------------------------------------- #
# Server entry point
# --------------------------------------------------------------------------- #
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:  # pragma: no cover
    """Run the local console. Binds to ``127.0.0.1`` (local-only) by default."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


# ASGI entry point (`uvicorn evidence_monitor.api:app`). Store + settings resolve lazily on first
# request, so importing this module performs no I/O.
app = create_app()


if __name__ == "__main__":  # pragma: no cover
    serve()


__all__ = ["app", "create_app", "get_store", "serve"]
