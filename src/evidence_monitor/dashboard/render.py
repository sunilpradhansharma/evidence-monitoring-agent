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
    LLMTarget,
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
# Dashboard view (Stage 2) — a richer, filter-driven overview built from the SAME read-only
# per-response scan as build_report. It adds NO capture/scoring/alert logic; it only re-shapes
# stored records into the dashboard's widgets. A "limited/dev" target (one that does not serve every
# persona — e.g. the provider-only PubMed+Claude stand-in) is classified per-target and, by default,
# excluded from the aggregate KPIs/charts so its small sample never silently skews the LLM picture.
# --------------------------------------------------------------------------- #

# Eight fixed sentiment buckets spanning the full -1..+1 scale (width 0.25). Display-only edges for
# the grouped histogram; the last bucket is inclusive of +1.0.
_BUCKET_EDGES: tuple[float, ...] = (-1.0, -0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0)
_BUCKET_COUNT = len(_BUCKET_EDGES) - 1

# How many flagged responses the dashboard's "recent alerts" strip shows (latest first).
_RECENT_ALERTS_LIMIT = 8


def _bucket_index(sentiment: float) -> int:
    """Map a sentiment in [-1, 1] to a histogram bucket index in [0, _BUCKET_COUNT-1]."""
    idx = int((sentiment + 1.0) / 0.25)
    return max(0, min(_BUCKET_COUNT - 1, idx))


def _iso_week(date_iso) -> str:
    """ISO-year/week label, e.g. ``2026-W24`` (groups volume-over-time by week)."""
    y, w, _ = date_iso.isocalendar()
    return f"{y}-W{w:02d}"


@dataclass(frozen=True)
class TargetMeta:
    """Per-target classification + display label, both sourced from config (Principle V).

    ``kind`` is the explicit config classification ("llm" | "synthesis" | "provider-api"); all kinds
    are first-class in the dashboard (no exclusion / no "dev" treatment). ``display_name`` is the
    config label (falling back to the llm_name). Content-agnostic: only structural provider
    ids / kinds / labels flow through — never brand/indication names.
    """

    target_id: str
    display_name: str
    kind: str


@dataclass(frozen=True)
class DashboardKpis:
    """The five KPI cards' numbers (over all targets, optionally narrowed by the LLM filter)."""

    responses_total: int = 0
    responses_captured: int = 0
    success_rate: float = 0.0
    scored: int = 0
    avg_sentiment: float = 0.0
    active_alerts: int = 0
    positioned: int = 0
    favourable: int = 0
    favourable_pct: float = 0.0
    last_run: Run | None = None


@dataclass(frozen=True)
class HistogramSeries:
    """One LLM's sentiment distribution across the fixed buckets (aligned to _BUCKET_EDGES)."""

    target_id: str
    counts: list[int]


@dataclass(frozen=True)
class PositionSeries:
    """One LLM's competitive-position counts (the frontend computes % share from counts/total)."""

    target_id: str
    counts: dict[str, int]
    total: int


@dataclass(frozen=True)
class HeatmapCell:
    """Mean sentiment for one (LLM x therapeutic-area) cell; ``mean`` is None when there is no data
    (rendered as n/a, never as a misleading 'absent/negative' score)."""

    therapeutic_area: str
    mean: float | None
    count: int


@dataclass(frozen=True)
class HeatmapRow:
    target_id: str
    cells: list[HeatmapCell]


@dataclass(frozen=True)
class WeekVolume:
    """Responses captured in one ISO week, split by status (all four statuses always present)."""

    week: str
    counts: dict[str, int]


@dataclass(frozen=True)
class RecentAlert:
    """A latest-first flagged response for the dashboard strip (drill-through by response_id)."""

    response_id: str
    question_id: str
    question_text: str
    model: str
    persona: str
    alert_type: str
    severity: int
    sentiment: float | None
    created_at: str
    rules: list[Alert]


@dataclass(frozen=True)
class DashboardData:
    """Everything the Dashboard page needs — KPIs, charts, target classification, filter context."""

    kpis: DashboardKpis
    targets: list[TargetMeta]
    bucket_edges: tuple[float, ...]
    histogram: list[HistogramSeries]
    positioning: list[PositionSeries]
    position_order: tuple[str, ...]
    therapeutic_areas: list[str]
    heatmap: list[HeatmapRow]
    volume_by_week: list[WeekVolume]
    recent_alerts: list[RecentAlert]
    options: ReportOptions
    filters: dict[str, str]


# Stable chart ordering by kind, then name. All kinds are first-class; this only groups the columns.
_KIND_RANK = {"llm": 0, "provider-api": 1, "synthesis": 2}


def target_metas(targets: list[LLMTarget] | None, llm_names: set[str]) -> dict[str, TargetMeta]:
    """Classify every llm_name, reading the explicit ``kind`` + ``display_name`` from config. Names
    not present in config default to kind 'llm' with the raw name as label. No persona heuristic."""
    by_name = {t.llm_name: t for t in (targets or [])}
    metas: dict[str, TargetMeta] = {}
    for name in llm_names:
        t = by_name.get(name)
        metas[name] = TargetMeta(
            target_id=name,
            display_name=(t.display_name or t.llm_name) if t is not None else name,
            kind=t.kind if t is not None else "llm",
        )
    return metas


def _ordered_targets(metas: dict[str, TargetMeta], present: set[str]) -> list[str]:
    """Chart series/row order: grouped by kind (llm, provider-api, synthesis) then name."""
    return sorted(present, key=lambda n: (_KIND_RANK.get(metas[n].kind, 9), n))


def build_dashboard(
    store: DataAccess,
    *,
    filters: QueryFilters | None = None,
    llms: set[str] | None = None,
    targets: list[LLMTarget] | None = None,
) -> DashboardData:
    """Aggregate the Dashboard widgets from the read-only response repository.

    ``filters`` (persona / therapeutic-area / date range / run) constrain the universe at the data
    layer; ``llms`` (the multi-select) is the only view-layer filter (the seam stays single-LLM).
    Every target is first-class — there is no kind-based exclusion — so the synthesis target appears
    alongside the LLMs by default. The full per-target classification (kind + display label) is
    returned so the UI can label each series from one source of truth.
    """
    filters = filters or QueryFilters()
    universe = store.responses.query(filters, page_size=None).items

    # Classify every target present in the persona/therapy/period universe (before the llm multi-
    # select) so the chart legend + the LLM filter stay stable regardless of the current selection.
    metas = target_metas(targets, {r.llm_name for r in universe})

    responses = [r for r in universe if llms is None or r.llm_name in llms]

    # Single pass: latest score per response feeds sentiment / position / heatmap; status feeds
    # volume + capture. Mirrors build_report's accumulation (no new judgement).
    scores: dict[str, ScoringRecord | None] = {}
    status_counts: Counter[ResponseStatus] = Counter()
    histogram: dict[str, list[int]] = defaultdict(lambda: [0] * _BUCKET_COUNT)
    position_counts: dict[str, Counter[str]] = defaultdict(Counter)
    heat: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])  # [sum, count]
    week_counts: dict[str, Counter[str]] = defaultdict(Counter)
    sentiment_total = 0.0
    scored = 0
    favourable = 0

    for r in responses:
        status_counts[r.status] += 1
        week_counts[_iso_week(r.timestamp_utc.date())][str(r.status)] += 1
        score = store.scores.latest_for(r.response_id)
        scores[r.response_id] = score
        if score is None:
            continue
        scored += 1
        sentiment_total += score.sentiment_score
        histogram[r.llm_name][_bucket_index(score.sentiment_score)] += 1
        position_counts[r.llm_name][str(score.competitive_position)] += 1
        if score.competitive_position in (
            CompetitivePosition.FIRST_LINE_RECOMMENDED,
            CompetitivePosition.AMONG_OPTIONS,
        ):
            favourable += 1
        cell = heat[(r.llm_name, r.therapeutic_area)]
        cell[0] += score.sentiment_score
        cell[1] += 1

    # Active alerts on the included, in-scope responses (same scoping as build_report).
    in_scope = {r.response_id for r in responses}
    alerts_by_response: dict[str, list[Alert]] = defaultdict(list)
    for a in store.alerts.list(order_by_severity=True):
        if a.response_id in in_scope:
            alerts_by_response[a.response_id].append(a)
    active_alerts = sum(len(a) for a in alerts_by_response.values())

    metrics = RunMetrics(
        total=len(responses),
        success=status_counts[ResponseStatus.SUCCESS],
        truncated=status_counts[ResponseStatus.TRUNCATED],
        failed=status_counts[ResponseStatus.FAILED],
        blocked=status_counts[ResponseStatus.BLOCKED],
    )
    # "Last run" must reflect the FILTERED view, not the globally newest run: a scoped run_id names
    # that run; otherwise it is the most-recent run that actually contributed to the in-view set.
    runs = store.runs.list()  # most-recent first
    if filters.run_id:
        last_run = store.runs.get(filters.run_id)
    else:
        in_view_run_ids = {r.run_id for r in responses}
        last_run = next((run for run in runs if run.run_id in in_view_run_ids), None)
    kpis = DashboardKpis(
        responses_total=metrics.total,
        responses_captured=metrics.captured,
        success_rate=metrics.capture_rate,
        scored=scored,
        avg_sentiment=(sentiment_total / scored if scored else 0.0),
        active_alerts=active_alerts,
        positioned=scored,
        favourable=favourable,
        favourable_pct=(favourable / scored if scored else 0.0),
        last_run=last_run,
    )

    present = {r.llm_name for r in responses}
    order = _ordered_targets(metas, present)
    therapy_areas = sorted({r.therapeutic_area for r in responses})

    histogram_series = [HistogramSeries(target_id=n, counts=histogram[n]) for n in order]
    positioning_series = [
        PositionSeries(
            target_id=n, counts=dict(position_counts[n]), total=sum(position_counts[n].values())
        )
        for n in order
    ]
    heatmap = [
        HeatmapRow(
            target_id=n,
            cells=[
                HeatmapCell(
                    therapeutic_area=ta,
                    mean=(heat[(n, ta)][0] / heat[(n, ta)][1] if heat[(n, ta)][1] else None),
                    count=int(heat[(n, ta)][1]),
                )
                for ta in therapy_areas
            ],
        )
        for n in order
    ]
    volume_by_week = [
        WeekVolume(
            week=wk,
            counts={s.value: week_counts[wk].get(s.value, 0) for s in ResponseStatus},
        )
        for wk in sorted(week_counts)
    ]

    recent = _recent_alerts(store, alerts_by_response, scores)

    return DashboardData(
        kpis=kpis,
        targets=[metas[n] for n in _ordered_targets(metas, set(metas))],
        bucket_edges=_BUCKET_EDGES,
        histogram=histogram_series,
        positioning=positioning_series,
        position_order=tuple(p.value for p in CompetitivePosition),
        therapeutic_areas=therapy_areas,
        heatmap=heatmap,
        volume_by_week=volume_by_week,
        recent_alerts=recent,
        options=_options(store),
        filters={k: v for k, v in _filter_echo(filters).items() if v},
    )


def _recent_alerts(
    store: DataAccess,
    alerts_by_response: dict[str, list[Alert]],
    scores: dict[str, ScoringRecord | None],
) -> list[RecentAlert]:
    """Build the latest-first 'recent alerts' strip from the in-scope flagged responses."""
    items: list[RecentAlert] = []
    q_cache: dict[str, Question | None] = {}
    for rid, alerts in alerts_by_response.items():
        response = store.responses.get(rid)
        if response is None:
            continue
        if response.question_id not in q_cache:
            q_cache[response.question_id] = store.questions.get(response.question_id)
        q = q_cache[response.question_id]
        top = max(alerts, key=lambda a: a.severity)
        score = scores.get(rid)
        latest_at = max((a.created_at for a in alerts), default=response.timestamp_utc)
        items.append(
            RecentAlert(
                response_id=rid,
                question_id=response.question_id,
                question_text=q.question_text if q is not None else "",
                model=response.llm_name,
                persona=str(response.persona),
                alert_type=_ALERT_TYPE.get(top.rule_fired, str(top.rule_fired)),
                severity=top.severity,
                sentiment=score.sentiment_score if score is not None else None,
                created_at=latest_at.isoformat(),
                rules=alerts,
            )
        )
    items.sort(key=lambda i: i.created_at, reverse=True)
    return items[:_RECENT_ALERTS_LIMIT]


# --------------------------------------------------------------------------- #
# Page feeds (Stage 3) — Responses table, Alerts feed, LLM Comparison. All read-only; each reuses
# the SAME store query path + latest-score / question-text lookups as the Reports view. No new
# capture/scoring/alert logic. Limited/dev targets are NOT filtered out here (these are full,
# auditable feeds); the frontend tags them. Aggregation stays content-agnostic.
# --------------------------------------------------------------------------- #
def _paginate(items: list, page: int, page_size: int) -> list:
    start = max(0, (page - 1) * page_size)
    return items[start : start + page_size]


@dataclass(frozen=True)
class ResponseRow:
    """One row of the Responses table (no full body — the body is fetched on row click)."""

    response_id: str
    timestamp_utc: str
    llm_name: str
    persona: str
    therapeutic_area: str
    domain: str
    status: str
    question_id: str
    question_text: str
    sentiment: float | None
    competitive_position: str | None
    citation_status: str | None
    has_alert: bool


@dataclass(frozen=True)
class ResponsesTable:
    items: list[ResponseRow]
    total: int
    page: int
    page_size: int


def filter_responses(
    store: DataAccess,
    *,
    filters: QueryFilters | None = None,
    llms: set[str] | None = None,
    search: str | None = None,
) -> list[Response]:
    """The Responses view's filtered row SET (no pagination, no enrichment): ``filters`` at the data
    layer, then the ``llms`` multi-select and free-text ``search`` as view-layer refinements. The
    SINGLE definition of "which responses match the Responses view" — shared by the paginated table
    and the CSV/JSON export so they can never diverge."""
    filters = filters or QueryFilters()
    rows = store.responses.query(filters, page_size=None).items
    if llms:
        rows = [r for r in rows if r.llm_name in llms]
    if search:
        needle = search.strip().lower()
        q_cache: dict[str, Question | None] = {}

        def _qt(qid: str) -> str:
            if qid not in q_cache:
                q_cache[qid] = store.questions.get(qid)
            q = q_cache[qid]
            return q.question_text if q is not None else ""

        rows = [
            r
            for r in rows
            if needle in r.question_id.lower()
            or needle in r.llm_name.lower()
            or needle in r.therapeutic_area.lower()
            or needle in str(r.persona).lower()
            or needle in str(r.status).lower()
            or needle in _qt(r.question_id).lower()
        ]
    return rows


def build_responses_table(
    store: DataAccess,
    *,
    filters: QueryFilters | None = None,
    llms: set[str] | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> ResponsesTable:
    """Filterable, paginated Responses table. Reuses :func:`filter_responses` for the row set (so
    the table and the export always agree), then enriches only the page slice with latest score +
    question text."""
    rows = filter_responses(store, filters=filters, llms=llms, search=search)
    alert_ids = {a.response_id for a in store.alerts.list()}
    q_cache: dict[str, Question | None] = {}

    def _qtext(qid: str) -> str:
        if qid not in q_cache:
            q_cache[qid] = store.questions.get(qid)
        q = q_cache[qid]
        return q.question_text if q is not None else ""

    total = len(rows)
    items: list[ResponseRow] = []
    for r in _paginate(rows, page, page_size):
        s = store.scores.latest_for(r.response_id)
        items.append(
            ResponseRow(
                response_id=r.response_id,
                timestamp_utc=r.timestamp_utc.isoformat(),
                llm_name=r.llm_name,
                persona=str(r.persona),
                therapeutic_area=r.therapeutic_area,
                domain=str(r.domain),
                status=str(r.status),
                question_id=r.question_id,
                question_text=_qtext(r.question_id),
                sentiment=s.sentiment_score if s is not None else None,
                competitive_position=str(s.competitive_position) if s is not None else None,
                citation_status=str(s.citation_status) if s is not None else None,
                has_alert=r.response_id in alert_ids,
            )
        )
    return ResponsesTable(items=items, total=total, page=page, page_size=page_size)


@dataclass(frozen=True)
class AlertFeedItem:
    alert_id: str
    response_id: str
    question_id: str
    question_text: str
    model: str
    persona: str
    therapeutic_area: str
    rule: str
    alert_type: str
    severity: int
    reason: str
    sentiment: float | None
    created_at: str


@dataclass(frozen=True)
class AlertsFeed:
    items: list[AlertFeedItem]
    total: int
    counts_by_rule: dict[str, int]
    counts_by_type: dict[str, int]


def build_alerts_feed(
    store: DataAccess,
    *,
    rule: str | None = None,
    persona: str | None = None,
    llm: str | None = None,
    severity: int | None = None,
    date_from=None,
    page: int = 1,
    page_size: int = 25,
) -> AlertsFeed:
    """Enriched, filterable, paginated alert feed.

    The per-type COUNTS (the KPI tiles) are computed over the RESPONSE-SCOPE filters (persona / llm
    / period) only — NOT the rule/severity drill filters — so the tiles show the breakdown for the
    current view and reconcile EXACTLY with the dashboard's ``active_alerts`` KPI for the same
    persona/llm/period. ``rule`` + ``severity`` then narrow the listed items without changing the
    tiles (so you can click between types). sum(counts_by_rule) == the scope's alert count."""
    alerts = store.alerts.list(order_by_severity=True)

    q_cache: dict[str, Question | None] = {}

    def _qtext(qid: str) -> str:
        if qid not in q_cache:
            q_cache[qid] = store.questions.get(qid)
        q = q_cache[qid]
        return q.question_text if q is not None else ""

    # Response-scope: the alerts whose response matches persona/llm/period. Tiles count over THIS.
    scoped: list[tuple[Alert, Response]] = []
    for a in alerts:
        r = store.responses.get(a.response_id)
        if r is None:
            continue
        if persona and str(r.persona) != persona:
            continue
        if llm and r.llm_name != llm:
            continue
        if date_from is not None and r.timestamp_utc < date_from:
            continue
        scoped.append((a, r))

    counts_by_rule = Counter(str(a.rule_fired) for a, _ in scoped)
    counts_by_type = Counter(_ALERT_TYPE.get(a.rule_fired, str(a.rule_fired)) for a, _ in scoped)

    enriched: list[AlertFeedItem] = []
    for a, r in scoped:
        if rule and str(a.rule_fired) != rule:
            continue
        if severity is not None and a.severity != severity:
            continue
        s = store.scores.latest_for(a.response_id)
        enriched.append(
            AlertFeedItem(
                alert_id=a.alert_id,
                response_id=a.response_id,
                question_id=r.question_id,
                question_text=_qtext(r.question_id),
                model=r.llm_name,
                persona=str(r.persona),
                therapeutic_area=r.therapeutic_area,
                rule=str(a.rule_fired),
                alert_type=_ALERT_TYPE.get(a.rule_fired, str(a.rule_fired)),
                severity=a.severity,
                reason=a.reason,
                sentiment=s.sentiment_score if s is not None else None,
                created_at=a.created_at.isoformat(),
            )
        )
    total = len(enriched)
    return AlertsFeed(
        items=_paginate(enriched, page, page_size),
        total=total,
        counts_by_rule=dict(counts_by_rule),
        counts_by_type=dict(counts_by_type),
    )


@dataclass(frozen=True)
class ComparisonColumn:
    response_id: str
    llm_name: str
    status: str
    finish_reason: str
    response_text: str
    block_reason: str | None
    sentiment: float | None
    competitive_position: str | None
    citation_status: str | None
    scoring_rationale: str | None


@dataclass(frozen=True)
class Comparison:
    question_id: str
    question_text: str
    persona: str
    run_id: str
    columns: list[ComparisonColumn]


def build_comparison(store: DataAccess, *, question_id: str, run_id: str) -> Comparison:
    """Every target's full answer (+ its score) for one question in one run, for side-by-side view.
    A target with no response simply has no column (correct for provider-only targets on non-
    provider questions); the frontend notes empty/failed answers rather than showing blanks."""
    rows = [
        r
        for r in store.responses.query(QueryFilters(run_id=run_id), page_size=None).items
        if r.question_id == question_id
    ]
    rows.sort(key=lambda r: r.llm_name)
    q = store.questions.get(question_id)
    columns: list[ComparisonColumn] = []
    for r in rows:
        s = store.scores.latest_for(r.response_id)
        columns.append(
            ComparisonColumn(
                response_id=r.response_id,
                llm_name=r.llm_name,
                status=str(r.status),
                finish_reason=str(r.finish_reason),
                response_text=r.response_text,
                block_reason=r.block_reason,
                sentiment=s.sentiment_score if s is not None else None,
                competitive_position=str(s.competitive_position) if s is not None else None,
                citation_status=str(s.citation_status) if s is not None else None,
                scoring_rationale=s.scoring_rationale if s is not None else None,
            )
        )
    return Comparison(
        question_id=question_id,
        question_text=q.question_text if q is not None else "",
        persona=str(q.persona) if q is not None else "",
        run_id=run_id,
        columns=columns,
    )


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
    "AlertFeedItem",
    "AlertsFeed",
    "ApprovalGate",
    "ApprovalOptions",
    "ApprovedQuestionsView",
    "Comparison",
    "ComparisonColumn",
    "CoverageCell",
    "CoverageRow",
    "DashboardData",
    "DashboardKpis",
    "FlaggedResponse",
    "ResponseRow",
    "ResponsesTable",
    "Headline",
    "HeatmapCell",
    "HeatmapRow",
    "HistogramSeries",
    "PositionSeries",
    "RecentAlert",
    "ReportData",
    "ReportOptions",
    "RunMetrics",
    "SentimentAgg",
    "TargetMeta",
    "WeekVolume",
    "build_alerts_feed",
    "build_approved_questions",
    "build_comparison",
    "build_dashboard",
    "build_report",
    "build_responses_table",
    "filter_responses",
    "latest_per_question",
    "target_metas",
    "render_app",
    "render_reports_section",
    "render_static_report",
    "write_static_report",
]
