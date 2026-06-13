"""FastAPI app — local-only service layer (US3 Approvals; US5 Reports/health added later).

**Reports are read-only; the only writes are local Medical Affairs Approvals** (Principle I).
No endpoint here submits a question to any LLM or takes any outward action — submission happens
only inside scheduled / CLI-triggered runs over APPROVED questions. The app is local-only for the
POC (no auth — out of scope).

The data store is dependency-injected: tests pass an in-memory :class:`SqliteStore`; in
production the store is built lazily from settings on first request, so importing this module has
no filesystem side effect.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from evidence_monitor.config.settings import get_settings
from evidence_monitor.data_access.interface import DataAccess
from evidence_monitor.data_access.models import (
    ApprovalStatus,
    Domain,
    Persona,
    Question,
)
from evidence_monitor.data_access.sqlite_store import SqliteStore
from evidence_monitor.question_repo.approval import ApprovalError
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
# Store wiring
# --------------------------------------------------------------------------- #
def get_store(request: Request) -> DataAccess:
    """Resolve the request's data store, building one from settings on first use if unset."""
    store = request.app.state.store
    if store is None:
        store = SqliteStore(get_settings().db_path)
        request.app.state.store = store
    return store


# FastAPI dependency alias (Annotated form keeps `Depends` out of argument defaults).
StoreDep = Annotated[DataAccess, Depends(get_store)]


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #
def create_app(store: DataAccess | None = None) -> FastAPI:
    """Build the FastAPI app. Pass ``store`` to inject one (tests); otherwise it is lazy."""
    app = FastAPI(title="Evidence Monitoring Agent — Local API")
    app.state.store = store
    _register_approvals(app)
    return app


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
    def approve_question(
        question_id: str,
        body: ApproveBody,
        store: StoreDep,
    ) -> Question:
        """Approve a question, recording the approver. 404 unknown; 409 if REJECTED (terminal)."""
        svc = QuestionService(store.questions)
        try:
            return svc.approve(question_id, body.approver_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ApprovalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/approvals/questions/{question_id}/reject")
    def reject_question(
        question_id: str,
        body: RejectBody,
        store: StoreDep,
    ) -> Question:
        """Reject a question (excluded from all runs). 404 unknown."""
        svc = QuestionService(store.questions)
        try:
            return svc.reject(question_id, body.approver_name, body.reason)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ApprovalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/approvals/questions/{question_id}/edit")
    def edit_question(
        question_id: str,
        body: EditBody,
        store: StoreDep,
    ) -> Question:
        """Edit a question — creates a NEW version (no hard delete, FR-001); returns it."""
        changes = body.model_dump(exclude_unset=True, exclude_none=True)
        if not changes:
            raise HTTPException(status_code=400, detail="no editable fields provided")
        svc = QuestionService(store.questions)
        try:
            return svc.edit(question_id, **changes)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


# ASGI entry point (`uvicorn evidence_monitor.api:app`). The store is resolved lazily on first
# request, so importing this module performs no I/O.
app = create_app()


__all__ = ["app", "create_app", "get_store"]
