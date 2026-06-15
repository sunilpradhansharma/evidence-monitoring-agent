"""Read-only JSON serializers for the React dashboard (Part A).

This module performs NO aggregation of its own — it only *surfaces* what is already computed.
Every figure comes from the SAME functions that back the server-rendered HTML in
:mod:`evidence_monitor.dashboard.render` — :func:`build_report`, :func:`build_approved_questions`,
and :func:`latest_per_question`. We call those, then serialize their value objects to plain dicts.

Strictly read-only: nothing here writes. Writes still go ONLY through the existing approve / reject
/ edit POST endpoints. Content-agnostic (Principle IV): brand / therapeutic-area / model / question
values flow through as opaque data — nothing is enumerated here.
"""

from __future__ import annotations

from evidence_monitor.dashboard.render import (
    DashboardData,
    ReportData,
    build_dashboard,
    build_report,
    latest_per_question,
)
from evidence_monitor.data_access.interface import DataAccess, QueryFilters
from evidence_monitor.data_access.models import ApprovalStatus, LLMTarget, Persona
from evidence_monitor.question_repo.repository import QuestionService

# active-flag rule per status, mirroring the server-rendered views: PENDING/APPROVED are the
# run-relevant active sets; REJECTED/ALL are not active-filtered (history is shown).
_ACTIVE_BY_STATUS: dict[ApprovalStatus, bool | None] = {
    ApprovalStatus.PENDING: True,
    ApprovalStatus.APPROVED: True,
    ApprovalStatus.REJECTED: None,
}


def runs_payload(store: DataAccess) -> list[dict]:
    """Runs for the run selector (most-recent first), with capture/fail counts."""
    return [
        {
            "run_id": r.run_id,
            "trigger_type": str(r.trigger_type),
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "responses_captured": r.responses_captured,
            "failure_count": r.failure_count,
        }
        for r in store.runs.list()
    ]


def _sentiment_rows(by_group: dict) -> list[dict]:
    return [
        {
            "name": name,
            "average": agg.average,
            "count": agg.count,
            "positive": agg.positive,
            "neutral": agg.neutral,
            "negative": agg.negative,
        }
        for name, agg in by_group.items()
    ]


def _report_to_dict(data: ReportData) -> dict:
    """Serialize a :class:`ReportData` (built by ``render.build_report``) to a JSON-ready dict."""
    m = data.metrics
    run = data.selected_run
    duration_seconds: float | None = None
    run_dict: dict | None = None
    if run is not None:
        if run.ended_at and run.started_at:
            duration_seconds = (run.ended_at - run.started_at).total_seconds()
        run_dict = {
            "run_id": run.run_id,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "ended_at": run.ended_at.isoformat() if run.ended_at else None,
            "duration_seconds": duration_seconds,
            "est_cost": run.est_cost,
            "total_tokens": run.total_tokens,
            "questions_attempted": run.questions_attempted,
            "responses_captured": run.responses_captured,
            "failure_count": run.failure_count,
        }

    return {
        "headline": data.headline.sentence if data.headline else "",
        "total_responses": data.total_responses,
        "metrics": {
            "total": m.total,
            "success": m.success,
            "truncated": m.truncated,
            "failed": m.failed,
            "blocked": m.blocked,
            "failed_blocked": m.failed_blocked,
            "captured": m.captured,
            "capture_rate": m.capture_rate,
            "capture_rate_pct": m.capture_rate_pct,
            "capture_ok": m.capture_ok,
            "capture_target_pct": m.capture_target_pct,
            "alert_count": data.alert_count,
            "alerts_by_type": data.alerts_by_type,
            "question_count": data.question_count,
            "model_count": data.model_count,
        },
        "approval_gate": {
            "approved": data.approval_gate.approved,
            "pending": data.approval_gate.pending,
            "rejected": data.approval_gate.rejected,
            "total": data.approval_gate.total,
        },
        "run": run_dict,
        "coverage": {
            "models": data.coverage_models,
            "rows": [
                {
                    "question_id": row.question_id,
                    "label": row.label,
                    "cells": [
                        {
                            "klass": cell.klass,
                            "label": cell.label,
                            "truncated": cell.truncated,
                            "response_id": cell.response_id,
                            "title": cell.title,
                        }
                        for cell in row.cells
                    ],
                }
                for row in data.coverage_rows
            ],
        },
        "sentiment_by_model": _sentiment_rows(data.sentiment_by_llm),
        "sentiment_by_therapy": _sentiment_rows(data.sentiment_by_therapy),
        "citation_counts": data.citation_counts,
        "positioning": {
            "order": list(data.position_order),
            "rows": [
                {"model": model, "counts": counts} for model, counts in data.position_by_llm.items()
            ],
        },
        "alerts": [
            {
                "response_id": f.response.response_id,
                "question_id": f.response.question_id,
                "question_text": f.question_text,
                "model": f.response.llm_name,
                "persona": str(f.response.persona),
                "severity": f.max_severity,
                "truncated": f.is_truncated,
                "rules": [
                    {"rule": str(a.rule_fired), "severity": a.severity, "reason": a.reason}
                    for a in f.alerts
                ],
            }
            for f in data.flagged
        ],
    }


def report_payload(store: DataAccess, run_id: str) -> dict:
    """Full Reports payload for one run. Raises ``KeyError`` if the run is unknown (→ 404)."""
    if store.runs.get(run_id) is None:
        raise KeyError(run_id)
    data = build_report(store, QueryFilters(run_id=run_id))
    return _report_to_dict(data)


def _dashboard_to_dict(data: DashboardData) -> dict:
    """Serialize a :class:`DashboardData` (from ``render.build_dashboard``) to a JSON dict.

    Pure serialization — every figure is already computed by ``build_dashboard``. Per-target
    classification (``is_full_llm`` / ``kind``) is surfaced so the frontend can tell a general LLM
    from a limited/dev target (e.g. the provider-only stand-in) and label it accordingly.
    """
    k = data.kpis
    run = k.last_run
    last_run = None
    if run is not None:
        last_run = {
            "run_id": run.run_id,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "ended_at": run.ended_at.isoformat() if run.ended_at else None,
            "responses_captured": run.responses_captured,
            "questions_attempted": run.questions_attempted,
            "total_tokens": run.total_tokens,
        }
    return {
        "include_dev": data.include_dev,
        "filters": data.filters,
        "options": {
            "personas": data.options.personas,
            "llms": data.options.llms,
            "therapeutic_areas": data.options.therapeutic_areas,
        },
        "targets": [
            {
                "target_id": t.target_id,
                "display_name": t.display_name,
                "is_full_llm": t.is_full_llm,
                "kind": t.kind,
            }
            for t in data.targets
        ],
        "kpis": {
            "responses_total": k.responses_total,
            "responses_captured": k.responses_captured,
            "success_rate": k.success_rate,
            "scored": k.scored,
            "avg_sentiment": k.avg_sentiment,
            "active_alerts": k.active_alerts,
            "positioned": k.positioned,
            "favourable": k.favourable,
            "favourable_pct": k.favourable_pct,
            "last_run": last_run,
        },
        "sentiment_histogram": {
            "bucket_edges": list(data.bucket_edges),
            "series": [{"target_id": s.target_id, "counts": s.counts} for s in data.histogram],
        },
        "positioning": {
            "order": list(data.position_order),
            "series": [
                {"target_id": s.target_id, "counts": s.counts, "total": s.total}
                for s in data.positioning
            ],
        },
        "heatmap": {
            "therapeutic_areas": data.therapeutic_areas,
            "rows": [
                {
                    "target_id": row.target_id,
                    "cells": [
                        {
                            "therapeutic_area": c.therapeutic_area,
                            "mean": c.mean,
                            "count": c.count,
                        }
                        for c in row.cells
                    ],
                }
                for row in data.heatmap
            ],
        },
        "volume_by_week": [{"week": w.week, "counts": w.counts} for w in data.volume_by_week],
        "recent_alerts": [
            {
                "response_id": a.response_id,
                "question_id": a.question_id,
                "question_text": a.question_text,
                "model": a.model,
                "persona": a.persona,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "sentiment": a.sentiment,
                "created_at": a.created_at,
                "rules": [
                    {"rule": str(r.rule_fired), "severity": r.severity, "reason": r.reason}
                    for r in a.rules
                ],
            }
            for a in data.recent_alerts
        ],
    }


def dashboard_payload(
    store: DataAccess,
    *,
    filters: QueryFilters | None = None,
    llms: set[str] | None = None,
    include_dev: bool = False,
    targets: list[LLMTarget] | None = None,
) -> dict:
    """Full Dashboard aggregate honoring the filter bar (read-only). Reuses ``build_dashboard``."""
    data = build_dashboard(
        store, filters=filters, llms=llms, include_dev=include_dev, targets=targets
    )
    return _dashboard_to_dict(data)


def _question_to_dict(q) -> dict:
    return {
        "question_id": q.question_id,
        "version": q.version,
        "persona": str(q.persona),
        "therapeutic_area": q.therapeutic_area,
        "domain": str(q.domain),
        "question_text": q.question_text,
        "approval_status": str(q.approval_status),
        "approver_name": q.approver_name,
        "approval_note": q.approval_note,
        "updated_at": q.updated_at.isoformat() if q.updated_at else None,
    }


def questions_payload(
    store: DataAccess, *, status: str | None = None, persona: str | None = None
) -> dict:
    """Version-aware questions for the Approvals tab + global status counts.

    ``status`` is one of PENDING/APPROVED/REJECTED/ALL (or unset → ALL). Counts are always global
    (latest version per question, regardless of the status/persona filter) so the tab header is
    stable. Each question appears exactly once at its current version (``latest_per_question``).
    """
    svc = QuestionService(store.questions)
    persona_enum = None
    if persona:
        try:
            persona_enum = Persona(persona)
        except ValueError:
            persona_enum = None

    # Global, version-aware counts (the dedup guarantee the HTML counts use).
    all_latest = latest_per_question(svc.list_questions())
    counts = {"pending": 0, "approved": 0, "rejected": 0, "total": len(all_latest)}
    for q in all_latest:
        if q.approval_status is ApprovalStatus.PENDING:
            counts["pending"] += 1
        elif q.approval_status is ApprovalStatus.APPROVED:
            counts["approved"] += 1
        elif q.approval_status is ApprovalStatus.REJECTED:
            counts["rejected"] += 1

    status_norm = (status or "ALL").upper()
    status_enum = {
        "PENDING": ApprovalStatus.PENDING,
        "APPROVED": ApprovalStatus.APPROVED,
        "REJECTED": ApprovalStatus.REJECTED,
    }.get(status_norm)

    rows = latest_per_question(
        svc.list_questions(
            approval_status=status_enum,
            active=_ACTIVE_BY_STATUS.get(status_enum) if status_enum else None,
            persona=persona_enum,
        )
    )
    rows.sort(key=lambda q: (str(q.persona), q.question_id))
    return {"counts": counts, "questions": [_question_to_dict(q) for q in rows]}


def response_payload(store: DataAccess, response_id: str) -> dict:
    """Full response text + latest scoring rationale for click-through. ``KeyError`` if unknown."""
    r = store.responses.get(response_id)
    if r is None:
        raise KeyError(response_id)
    score = store.scores.latest_for(response_id)
    score_dict = None
    if score is not None:
        score_dict = {
            "sentiment_score": score.sentiment_score,
            "competitive_position": str(score.competitive_position),
            "citation_status": str(score.citation_status),
            "scoring_rationale": score.scoring_rationale,
            "brand_mentions": list(score.brand_mentions),
            "key_claims": list(score.key_claims),
        }
    return {
        "response_id": r.response_id,
        "question_id": r.question_id,
        "llm_name": r.llm_name,
        "persona": str(r.persona),
        "therapeutic_area": r.therapeutic_area,
        "status": str(r.status),
        "finish_reason": str(r.finish_reason),
        "response_text": r.response_text,
        "block_reason": r.block_reason,
        "score": score_dict,
    }


__all__ = [
    "dashboard_payload",
    "questions_payload",
    "report_payload",
    "response_payload",
    "runs_payload",
]
