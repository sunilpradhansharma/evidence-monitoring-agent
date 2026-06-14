"""Reports view: aggregation + HTML rendering (US5 — FR-023/FR-024/FR-603).

This is the single source of the Reports view. The same render path produces BOTH:

- the **self-contained static export** (``render_static_report`` → one shareable ``.html`` file
  with inline CSS, no server required — FR-603), and
- the **served Reports tab** (``render_app`` embeds the identical section partial inside the
  tabbed local web app).

Everything here is **read-only**: it queries the response repository through the data-access seam
and never writes. Aggregation is content-agnostic (Principle IV) — brand / therapeutic-area / LLM
values flow through as opaque data; nothing is enumerated. Untrusted text (response bodies,
rationales) is auto-escaped by Jinja before it reaches the page.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from evidence_monitor.data_access.interface import DataAccess, QueryFilters
from evidence_monitor.data_access.models import (
    Alert,
    ApprovalStatus,
    CompetitivePosition,
    Domain,
    Persona,
    Question,
    ScoringRecord,
)
from evidence_monitor.question_repo.repository import QuestionService
from evidence_monitor.response_repo.schema import Response

# Sentiment buckets for the distribution view. Mirrors the default alert margins so the picture a
# stakeholder sees lines up with what the deterministic rules act on (these are display-only).
_POSITIVE_AT = 0.3
_NEGATIVE_AT = -0.3

_TEMPLATE_DIR = Path(__file__).resolve().parent


@lru_cache
def _env() -> Environment:
    """Process-cached Jinja environment loading templates from this package directory."""
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


# --------------------------------------------------------------------------- #
# Aggregates (plain value objects — the template only reads them)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SentimentAgg:
    """Sentiment distribution for one group (one LLM, or one therapeutic area)."""

    count: int = 0
    total: float = 0.0
    positive: int = 0
    neutral: int = 0
    negative: int = 0

    @property
    def average(self) -> float:
        return self.total / self.count if self.count else 0.0


@dataclass(frozen=True)
class FlaggedResponse:
    """A response that raised at least one alert, with the evidence for drill-down (FR-024)."""

    response: Response
    score: ScoringRecord | None
    alerts: list[Alert]

    @property
    def max_severity(self) -> int:
        return max((a.severity for a in self.alerts), default=0)


@dataclass(frozen=True)
class ReportOptions:
    """Choices for the filter form (built from the full, unfiltered response set)."""

    personas: list[str] = field(default_factory=lambda: [p.value for p in Persona])
    domains: list[str] = field(default_factory=lambda: [d.value for d in Domain])
    llms: list[str] = field(default_factory=list)
    therapeutic_areas: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReportData:
    """Everything the Reports view needs — the four sections plus filter context."""

    total_responses: int
    sentiment_by_llm: dict[str, SentimentAgg]
    sentiment_by_therapy: dict[str, SentimentAgg]
    position_by_llm: dict[str, dict[str, int]]
    alert_count: int
    flagged: list[FlaggedResponse]
    volume_by_date: dict[str, int]
    filters: dict[str, str]
    options: ReportOptions

    # The enum order is the canonical column order for the competitive-positioning table.
    position_order: tuple[str, ...] = tuple(p.value for p in CompetitivePosition)


# --------------------------------------------------------------------------- #
# Aggregation (read-only)
# --------------------------------------------------------------------------- #
def _accumulate(agg: SentimentAgg, sentiment: float) -> SentimentAgg:
    bucket = (
        "positive"
        if sentiment >= _POSITIVE_AT
        else "negative"
        if sentiment <= _NEGATIVE_AT
        else "neutral"
    )
    return SentimentAgg(
        count=agg.count + 1,
        total=agg.total + sentiment,
        positive=agg.positive + (bucket == "positive"),
        neutral=agg.neutral + (bucket == "neutral"),
        negative=agg.negative + (bucket == "negative"),
    )


def _options(store: DataAccess) -> ReportOptions:
    """Filter choices from the FULL response set so the dropdowns stay stable across filtering."""
    everything = store.responses.query(QueryFilters(), page_size=None).items
    return ReportOptions(
        llms=sorted({r.llm_name for r in everything}),
        therapeutic_areas=sorted({r.therapeutic_area for r in everything}),
    )


def build_report(store: DataAccess, filters: QueryFilters | None = None) -> ReportData:
    """Aggregate the four Reports sections from the (read-only) response repository.

    ``filters`` constrains every section consistently (persona / TA / LLM / date range, etc.).
    A response with no scoring record yet still counts toward volume but not toward the
    sentiment / competitive-position aggregates.
    """
    filters = filters or QueryFilters()
    responses = store.responses.query(filters, page_size=None).items

    sentiment_by_llm: dict[str, SentimentAgg] = defaultdict(SentimentAgg)
    sentiment_by_therapy: dict[str, SentimentAgg] = defaultdict(SentimentAgg)
    position_by_llm: dict[str, Counter[str]] = defaultdict(Counter)
    volume_by_date: Counter[str] = Counter()

    scores: dict[str, ScoringRecord | None] = {}
    for r in responses:
        volume_by_date[r.timestamp_utc.date().isoformat()] += 1
        score = store.scores.latest_for(r.response_id)
        scores[r.response_id] = score
        if score is None:
            continue
        sentiment_by_llm[r.llm_name] = _accumulate(
            sentiment_by_llm[r.llm_name], score.sentiment_score
        )
        sentiment_by_therapy[r.therapeutic_area] = _accumulate(
            sentiment_by_therapy[r.therapeutic_area], score.sentiment_score
        )
        position_by_llm[r.llm_name][str(score.competitive_position)] += 1

    # Flagged responses: alerts grouped by response, restricted to the filtered set, severity-first.
    in_scope = {r.response_id: r for r in responses}
    alerts_by_response: dict[str, list[Alert]] = defaultdict(list)
    for a in store.alerts.list(order_by_severity=True):
        if a.response_id in in_scope:
            alerts_by_response[a.response_id].append(a)
    flagged = [
        FlaggedResponse(response=in_scope[rid], score=scores.get(rid), alerts=alerts)
        for rid, alerts in alerts_by_response.items()
    ]
    flagged.sort(key=lambda f: (-f.max_severity, f.response.response_id))

    return ReportData(
        total_responses=len(responses),
        sentiment_by_llm=dict(sentiment_by_llm),
        sentiment_by_therapy=dict(sentiment_by_therapy),
        position_by_llm={llm: dict(c) for llm, c in position_by_llm.items()},
        alert_count=sum(len(a) for a in alerts_by_response.values()),
        flagged=flagged,
        volume_by_date=dict(sorted(volume_by_date.items())),
        filters={k: v for k, v in _filter_echo(filters).items() if v},
        options=_options(store),
    )


def _filter_echo(filters: QueryFilters) -> dict[str, str]:
    """The applied filter values, as strings, for echoing into the form / static header."""
    return {
        "persona": str(filters.persona) if filters.persona else "",
        "therapeutic_area": filters.therapeutic_area or "",
        "llm": filters.llm or "",
        "date_from": filters.date_from.date().isoformat() if filters.date_from else "",
        "date_to": filters.date_to.date().isoformat() if filters.date_to else "",
    }


# --------------------------------------------------------------------------- #
# Approved-questions view (Approvals tab, READ-ONLY) — through the question-repo read path
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ApprovalOptions:
    """Filter-dropdown choices for the approved-questions view (content-agnostic enums + the
    therapeutic areas actually present in the approved set)."""

    personas: list[str] = field(default_factory=lambda: [p.value for p in Persona])
    domains: list[str] = field(default_factory=lambda: [d.value for d in Domain])
    therapeutic_areas: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ApprovedQuestionsView:
    """Everything the read-only approved-questions section needs: the filtered rows (current
    versions only), the count for the header, the dropdown options, and the echoed filters."""

    questions: list[Question]
    total: int
    options: ApprovalOptions
    filters: dict[str, str]


def build_approved_questions(
    store: DataAccess,
    *,
    persona: str | None = None,
    therapeutic_area: str | None = None,
    domain: str | None = None,
    search: str | None = None,
) -> ApprovedQuestionsView:
    """Assemble the read-only APPROVED + active question view via the question-repository read path.

    Reads through :meth:`QuestionService.list_questions` (the same path the Approvals API uses) —
    never SQL — and applies the persona / therapeutic-area / domain / free-text filters and the
    stable ``question_id`` sort as view logic. ``search`` matches ``question_id`` or
    ``question_text`` case-insensitively. Only current (latest) versions are returned; history is
    not fabricated.
    """
    approved = QuestionService(store.questions).list_questions(
        approval_status=ApprovalStatus.APPROVED, active=True
    )
    options = ApprovalOptions(
        therapeutic_areas=sorted({q.therapeutic_area for q in approved}),
    )

    rows = approved
    if persona:
        rows = [q for q in rows if str(q.persona) == persona]
    if therapeutic_area:
        rows = [q for q in rows if q.therapeutic_area == therapeutic_area]
    if domain:
        rows = [q for q in rows if str(q.domain) == domain]
    if search:
        needle = search.strip().lower()
        rows = [
            q
            for q in rows
            if needle in q.question_id.lower() or needle in q.question_text.lower()
        ]
    rows = sorted(rows, key=lambda q: q.question_id)

    applied = {
        "persona": persona or "",
        "therapeutic_area": therapeutic_area or "",
        "domain": domain or "",
        "search": search or "",
    }
    return ApprovedQuestionsView(
        questions=rows,
        total=len(rows),
        options=options,
        filters={k: v for k, v in applied.items() if v},
    )


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_reports_section(data: ReportData, *, interactive: bool) -> str:
    """Render the four-section Reports fragment (shared by the served tab and the static export).

    ``interactive=True`` renders the live GET filter form; ``False`` renders the applied filters as
    static text (the export has no server to submit to).
    """
    return _env().get_template("reports_section.html").render(data=data, interactive=interactive)


def render_static_report(data: ReportData, *, generated_at: str | None = None) -> str:
    """Render the self-contained, shareable Reports HTML document (FR-603)."""
    return (
        _env()
        .get_template("static_report.html")
        .render(data=data, generated_at=generated_at, interactive=False)
    )


def render_app(
    data: ReportData,
    *,
    pending_questions: list[Question],
    approved_view: ApprovedQuestionsView | None = None,
    active_tab: str = "reports",
    score_review_enabled: bool = False,
) -> str:
    """Render the tabbed local web app (Reports + Approvals + scaffolded Score-review).

    ``approved_view`` feeds the read-only "Approved questions (N)" section on the Approvals tab.
    """
    return (
        _env()
        .get_template("template.html")
        .render(
            data=data,
            pending=pending_questions,
            approved=approved_view,
            active_tab=active_tab,
            score_review_enabled=score_review_enabled,
            interactive=True,
        )
    )


def write_static_report(
    store: DataAccess,
    out_path: str | Path,
    *,
    filters: QueryFilters | None = None,
    generated_at: str | None = None,
) -> Path:
    """Build and write the self-contained Reports export to ``out_path``; returns the path."""
    html = render_static_report(build_report(store, filters), generated_at=generated_at)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


__all__ = [
    "ApprovalOptions",
    "ApprovedQuestionsView",
    "FlaggedResponse",
    "ReportData",
    "ReportOptions",
    "SentimentAgg",
    "build_approved_questions",
    "build_report",
    "render_app",
    "render_reports_section",
    "render_static_report",
    "write_static_report",
]
