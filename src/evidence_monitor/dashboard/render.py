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

The presentation layer is intentionally rich (a headline band, a question x model coverage map, a
citation-status panel, per-run summary cards) but it derives EVERYTHING from existing stored
records — it adds no scoring, capture, or alert logic. Counts of questions always use the
version-aware ``QuestionService.list_questions`` read path (latest version per question); per-run
response metrics are scoped to the responses already filtered to the chosen ``run_id``.
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
    AlertRule,
    ApprovalStatus,
    CitationStatus,
    CompetitivePosition,
    Domain,
    Persona,
    Question,
    ResponseStatus,
    Run,
    ScoringRecord,
)
from evidence_monitor.question_repo.repository import QuestionService
from evidence_monitor.response_repo.schema import Response

# Sentiment buckets for the distribution view. Mirrors the default alert margins so the picture a
# stakeholder sees lines up with what the deterministic rules act on (these are display-only).
_POSITIVE_AT = 0.3
_NEGATIVE_AT = -0.3

# The ≥95% successful-capture target (SC-003 / FR-030). Display-only here.
_CAPTURE_TARGET = 0.95

_TEMPLATE_DIR = Path(__file__).resolve().parent

# Coverage-map cell classes (how a model represented the therapy). Display-only labels derived
# from the stored score — NOT a new judgement. Plain strings so the template can key CSS off them.
_CELL_FAVORABLE = "favorable"
_CELL_PARTIAL = "partial"
_CELL_NEGATIVE = "negative"
_CELL_ABSENT = "absent"
_CELL_WRONG = "wrong_indication"
_CELL_NODATA = "nodata"  # failed / blocked / no answer — distinct from "absent" (not mentioned)


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
    question_text: str = ""  # resolved via the question-repo read path for the flagged list

    @property
    def max_severity(self) -> int:
        return max((a.severity for a in self.alerts), default=0)

    @property
    def is_truncated(self) -> bool:
        return self.response.status is ResponseStatus.TRUNCATED


@dataclass(frozen=True)
class RunMetrics:
    """Per-run (or per-view) capture metrics for the summary cards. Scoped to the responses already
    filtered to the chosen ``run_id`` — nothing here is recomputed from a naive scan."""

    total: int = 0
    success: int = 0
    truncated: int = 0
    failed: int = 0
    blocked: int = 0

    @property
    def failed_blocked(self) -> int:
        return self.failed + self.blocked

    @property
    def captured(self) -> int:
        """Usable text preserved (full or partial): SUCCESS + TRUNCATED."""
        return self.success + self.truncated

    @property
    def capture_rate(self) -> float:
        return self.captured / self.total if self.total else 0.0

    @property
    def capture_rate_pct(self) -> float:
        return 100.0 * self.capture_rate

    @property
    def capture_ok(self) -> bool:
        return self.total > 0 and self.capture_rate >= _CAPTURE_TARGET

    capture_target_pct: float = 100.0 * _CAPTURE_TARGET


@dataclass(frozen=True)
class CoverageCell:
    """One question x model cell: how that model represented the therapy (derived, display-only)."""

    klass: str = _CELL_NODATA
    response_id: str | None = None
    truncated: bool = False
    title: str = "no response"  # hover text explaining the cell
    label: str = "—"  # short status word shown inside the filled cell


@dataclass(frozen=True)
class CoverageRow:
    """One row of the coverage map: a question and its cells aligned to the model columns."""

    question_id: str
    label: str
    cells: list[CoverageCell] = field(default_factory=list)


@dataclass(frozen=True)
class ApprovalGate:
    """Version-aware approval-gate counts (latest version per question — FR-001/FR-003)."""

    approved: int = 0
    pending: int = 0
    rejected: int = 0

    @property
    def total(self) -> int:
        return self.approved + self.pending + self.rejected


@dataclass(frozen=True)
class Headline:
    """One plain-language sentence summarizing the selected run for the top band."""

    sentence: str
    avg_sentiment: float = 0.0
    flagged_count: int = 0
    scored: int = 0


@dataclass(frozen=True)
class ReportOptions:
    """Choices for the filter form (built from the full, unfiltered response set)."""

    personas: list[str] = field(default_factory=lambda: [p.value for p in Persona])
    domains: list[str] = field(default_factory=lambda: [d.value for d in Domain])
    llms: list[str] = field(default_factory=list)
    therapeutic_areas: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReportData:
    """Everything the Reports view needs — the sections plus filter context."""

    total_responses: int
    sentiment_by_llm: dict[str, SentimentAgg]
    sentiment_by_therapy: dict[str, SentimentAgg]
    position_by_llm: dict[str, dict[str, int]]
    alert_count: int
    flagged: list[FlaggedResponse]
    volume_by_date: dict[str, int]
    filters: dict[str, str]
    options: ReportOptions
    runs: list[Run] = field(default_factory=list)  # for the Run-scope dropdown (most-recent first)

    # Presentation-layer aggregates (all derived from the records above; display-only).
    metrics: RunMetrics = field(default_factory=RunMetrics)
    headline: Headline | None = None
    selected_run: Run | None = None
    coverage_models: list[str] = field(default_factory=list)
    coverage_rows: list[CoverageRow] = field(default_factory=list)
    citation_counts: dict[str, int] = field(default_factory=dict)
    alerts_by_type: dict[str, int] = field(default_factory=dict)
    approval_gate: ApprovalGate = field(default_factory=ApprovalGate)
    question_count: int = 0
    model_count: int = 0

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


# Map an alert rule to a stakeholder-friendly type for the by-type breakdown (content-agnostic).
_ALERT_TYPE: dict[AlertRule, str] = {
    AlertRule.NEGATIVE_SENTIMENT: "sentiment",
    AlertRule.NOT_RECOMMENDED: "competitive",
    AlertRule.COMPETITOR_HIGHER: "competitive",
    AlertRule.WRONG_INDICATION: "wrong-indication",
}


def _classify_cell(
    response: Response, score: ScoringRecord | None, has_alert: bool
) -> CoverageCell:
    """Derive a coverage-map cell from an existing response + its latest score. Display-only — it
    re-reads the stored score, it never re-scores."""
    truncated = response.status is ResponseStatus.TRUNCATED
    # No usable answer: failed / blocked / empty-status → distinct "no data" cell.
    if response.status in (ResponseStatus.FAILED, ResponseStatus.BLOCKED):
        reason = (
            "blocked by provider safety filter"
            if response.status is ResponseStatus.BLOCKED
            else "capture failed after retries"
        )
        return CoverageCell(_CELL_NODATA, response.response_id, truncated, reason, "No answer")
    if score is None:
        return CoverageCell(
            _CELL_ABSENT, response.response_id, truncated, "captured, not scored yet", "Unscored"
        )

    pos = score.competitive_position
    sentiment = score.sentiment_score
    base = f"sentiment {sentiment:+.2f}, {pos.value}"
    if score.citation_status is CitationStatus.WRONG_INDICATION:
        return CoverageCell(
            _CELL_WRONG,
            response.response_id,
            truncated,
            f"wrong indication — {base}",
            "Wrong indication",
        )
    if has_alert or pos is CompetitivePosition.NOT_RECOMMENDED or sentiment <= _NEGATIVE_AT:
        label = "2nd-line" if pos is CompetitivePosition.SECOND_LINE else "Negative"
        return CoverageCell(
            _CELL_NEGATIVE, response.response_id, truncated, f"flagged — {base}", label
        )
    if pos is CompetitivePosition.NOT_MENTIONED:
        return CoverageCell(
            _CELL_ABSENT, response.response_id, truncated, f"not mentioned — {base}", "Absent"
        )
    if sentiment >= _POSITIVE_AT or pos is CompetitivePosition.FIRST_LINE_RECOMMENDED:
        label = (
            "First-line"
            if pos is CompetitivePosition.FIRST_LINE_RECOMMENDED
            else ("Cited" if score.citation_status is CitationStatus.CITED else "Favorable")
        )
        return CoverageCell(
            _CELL_FAVORABLE, response.response_id, truncated, f"favorable — {base}", label
        )
    return CoverageCell(
        _CELL_PARTIAL, response.response_id, truncated, f"partial — {base}", "Partial"
    )


def _short_label(text: str, *, limit: int = 48) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _headline_sentence(
    *, scored: int, avg: float, flagged: int, competitor_ahead: int, absent: int, scope: str
) -> str:
    """A plain-language summary of the selected run (content-agnostic — no brand names)."""
    if scored == 0:
        return f"No scored responses in {scope} yet — capture has run but scoring has not."
    lead = f"Across {scope}, average sentiment toward the therapy is {avg:+.2f}"
    if flagged == 0:
        return lead + " and no responses are flagged."
    why: list[str] = []
    if competitor_ahead:
        why.append(f"a competitor is rated higher on {competitor_ahead}")
        why[-1] += " response" + ("s" if competitor_ahead != 1 else "")
    if absent:
        why.append(f"the therapy is not mentioned on {absent}")
    tail = f" ({'; '.join(why)})" if why else ""
    plural = "responses are" if flagged != 1 else "response is"
    return f"{lead} and {flagged} {plural} flagged{tail}."


def build_report(store: DataAccess, filters: QueryFilters | None = None) -> ReportData:
    """Aggregate every Reports section from the (read-only) response repository.

    ``filters`` constrains every section consistently (run / persona / TA / LLM / date range, etc.).
    A response with no scoring record yet still counts toward volume but not toward the
    sentiment / competitive-position aggregates. The approval-gate counts are version-aware and
    global (the eligibility picture is a property of the question repository, not of one run).
    """
    filters = filters or QueryFilters()
    responses = store.responses.query(filters, page_size=None).items

    sentiment_by_llm: dict[str, SentimentAgg] = defaultdict(SentimentAgg)
    sentiment_by_therapy: dict[str, SentimentAgg] = defaultdict(SentimentAgg)
    position_by_llm: dict[str, Counter[str]] = defaultdict(Counter)
    volume_by_date: Counter[str] = Counter()
    citation_counts: Counter[str] = Counter()
    status_counts: Counter[ResponseStatus] = Counter()
    sentiment_total = 0.0
    scored = 0

    scores: dict[str, ScoringRecord | None] = {}
    for r in responses:
        status_counts[r.status] += 1
        volume_by_date[r.timestamp_utc.date().isoformat()] += 1
        score = store.scores.latest_for(r.response_id)
        scores[r.response_id] = score
        if score is None:
            continue
        scored += 1
        sentiment_total += score.sentiment_score
        citation_counts[str(score.citation_status)] += 1
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
    alerts_by_type: Counter[str] = Counter()
    for a in store.alerts.list(order_by_severity=True):
        if a.response_id in in_scope:
            alerts_by_response[a.response_id].append(a)
            alerts_by_type[_ALERT_TYPE.get(a.rule_fired, str(a.rule_fired))] += 1

    # Question text for the flagged list + coverage labels, via the version-aware read path.
    question_ids = {r.question_id for r in responses}
    q_lookup: dict[str, Question | None] = {qid: store.questions.get(qid) for qid in question_ids}

    def _qtext(qid: str) -> str:
        q = q_lookup.get(qid)
        return q.question_text if q is not None else ""

    flagged = [
        FlaggedResponse(
            response=in_scope[rid],
            score=scores.get(rid),
            alerts=alerts,
            question_text=_qtext(in_scope[rid].question_id),
        )
        for rid, alerts in alerts_by_response.items()
    ]
    flagged.sort(key=lambda f: (-f.max_severity, f.response.response_id))

    # Coverage map (question x model): one cell per (question, model), latest response wins.
    models = sorted({r.llm_name for r in responses})
    by_cell: dict[tuple[str, str], Response] = {}
    for r in responses:
        key = (r.question_id, r.llm_name)
        prev = by_cell.get(key)
        if prev is None or r.timestamp_utc >= prev.timestamp_utc:
            by_cell[key] = r
    coverage_rows: list[CoverageRow] = []
    competitor_ahead = sum(
        1
        for alist in alerts_by_response.values()
        for a in alist
        if a.rule_fired is AlertRule.COMPETITOR_HIGHER
    )
    absent_count = sum(
        1
        for r in responses
        if (s := scores.get(r.response_id)) is not None
        and s.competitive_position is CompetitivePosition.NOT_MENTIONED
    )
    for qid in sorted(question_ids):
        cells: list[CoverageCell] = []
        for m in models:
            resp = by_cell.get((qid, m))
            if resp is None:
                cells.append(
                    CoverageCell(_CELL_NODATA, None, False, "no response in this run", "—")
                )
                continue
            has_alert = bool(alerts_by_response.get(resp.response_id))
            cells.append(_classify_cell(resp, scores.get(resp.response_id), has_alert))
        label = _short_label(_qtext(qid)) or qid
        coverage_rows.append(CoverageRow(question_id=qid, label=label, cells=cells))

    metrics = RunMetrics(
        total=len(responses),
        success=status_counts[ResponseStatus.SUCCESS],
        truncated=status_counts[ResponseStatus.TRUNCATED],
        failed=status_counts[ResponseStatus.FAILED],
        blocked=status_counts[ResponseStatus.BLOCKED],
    )

    selected_run = store.runs.get(filters.run_id) if filters.run_id else None
    scope = "this run" if selected_run is not None else "this view"
    avg = sentiment_total / scored if scored else 0.0
    headline = Headline(
        sentence=_headline_sentence(
            scored=scored,
            avg=avg,
            flagged=len(flagged),
            competitor_ahead=competitor_ahead,
            absent=absent_count,
            scope=scope,
        ),
        avg_sentiment=avg,
        flagged_count=len(flagged),
        scored=scored,
    )

    # Citation counts — show all four statuses even when zero, in a stable order.
    citation_full = {c.value: citation_counts.get(c.value, 0) for c in CitationStatus}

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
        runs=store.runs.list(),
        metrics=metrics,
        headline=headline,
        selected_run=selected_run,
        coverage_models=models,
        coverage_rows=coverage_rows,
        citation_counts=citation_full,
        alerts_by_type=dict(sorted(alerts_by_type.items())),
        approval_gate=_approval_gate(store),
        question_count=len(question_ids),
        model_count=len(models),
    )


def latest_per_question(questions: list[Question]) -> list[Question]:
    """Defensive version-aware selector for ROW RENDERING: keep exactly one row per ``question_id``
    (the highest version). The store's read path is already latest-only (the ``(question_id,
    version)`` primary key makes duplicate versions impossible), but applying this at the render
    boundary guarantees a list can NEVER leak version history — the same guarantee the counts use.
    Preserves input order of first appearance so an upstream sort is respected."""
    by_id: dict[str, Question] = {}
    for q in questions:
        current = by_id.get(q.question_id)
        if current is None or q.version > current.version:
            by_id[q.question_id] = q
    return list(by_id.values())


def _approval_gate(store: DataAccess) -> ApprovalGate:
    """Version-aware approval-gate counts via the question-repo read path (latest version per
    question). A naive scan of the immutable version history would over-count (FR-001)."""
    latest = latest_per_question(QuestionService(store.questions).list_questions())
    by_status = Counter(q.approval_status for q in latest)
    return ApprovalGate(
        approved=by_status[ApprovalStatus.APPROVED],
        pending=by_status[ApprovalStatus.PENDING],
        rejected=by_status[ApprovalStatus.REJECTED],
    )


def _filter_echo(filters: QueryFilters) -> dict[str, str]:
    """The applied filter values, as strings, for echoing into the form / static header."""
    return {
        "run_id": filters.run_id or "",
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
    approved = latest_per_question(
        QuestionService(store.questions).list_questions(
            approval_status=ApprovalStatus.APPROVED, active=True
        )
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
            q for q in rows if needle in q.question_id.lower() or needle in q.question_text.lower()
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
    """Render the Reports fragment (shared by the served tab and the static export).

    ``interactive=True`` renders the live GET filter form and click-through links; ``False`` renders
    the applied filters as static text (the export has no server to submit to).
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
    rejected_questions: list[Question] | None = None,
    status_filter: str = "PENDING",
    persona_filter: str = "",
    active_tab: str = "reports",
    score_review_enabled: bool = False,
) -> str:
    """Render the tabbed local web app (Reports + Approvals).

    ``approved_view`` feeds the read-only "Approved questions (N)" section on the Approvals tab;
    ``rejected_questions`` feeds the read-only rejected list shown when that status is selected.
    """
    return (
        _env()
        .get_template("template.html")
        .render(
            data=data,
            pending=pending_questions,
            approved=approved_view,
            rejected=rejected_questions or [],
            status_filter=status_filter,
            persona_filter=persona_filter,
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
    "ApprovalGate",
    "ApprovalOptions",
    "ApprovedQuestionsView",
    "CoverageCell",
    "CoverageRow",
    "FlaggedResponse",
    "Headline",
    "ReportData",
    "ReportOptions",
    "RunMetrics",
    "SentimentAgg",
    "build_approved_questions",
    "build_report",
    "latest_per_question",
    "render_app",
    "render_reports_section",
    "render_static_report",
    "write_static_report",
]
