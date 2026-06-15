// Typed client for the read-only JSON API (/api/*) and the existing approval write endpoints.
// Writes reuse the SAME POST endpoints the server-rendered UI uses — no new write paths.

export interface RunSummary {
  run_id: string;
  trigger_type: string;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  questions_attempted: number;
  responses_captured: number;
  failure_count: number;
  total_tokens: number;
  est_cost: number;
  alert_count: number;
  status: string; // RUNNING | PARTIAL | COMPLETED
}

export interface Metrics {
  total: number;
  success: number;
  truncated: number;
  failed: number;
  blocked: number;
  failed_blocked: number;
  captured: number;
  capture_rate: number;
  capture_rate_pct: number;
  capture_ok: boolean;
  capture_target_pct: number;
  alert_count: number;
  alerts_by_type: Record<string, number>;
  question_count: number;
  model_count: number;
}

export interface ApprovalGate {
  approved: number;
  pending: number;
  rejected: number;
  total: number;
}

export interface RunMeta {
  run_id: string;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  est_cost: number;
  total_tokens: number;
  questions_attempted: number;
  responses_captured: number;
  failure_count: number;
}

export interface CoverageCell {
  klass: string;
  label: string;
  truncated: boolean;
  response_id: string | null;
  title: string;
}

export interface CoverageRow {
  question_id: string;
  label: string;
  cells: CoverageCell[];
}

export interface SentimentRow {
  name: string;
  average: number;
  count: number;
  positive: number;
  neutral: number;
  negative: number;
}

export interface AlertItem {
  response_id: string;
  question_id: string;
  question_text: string;
  model: string;
  persona: string;
  severity: number;
  truncated: boolean;
  rules: { rule: string; severity: number; reason: string }[];
}

export interface Report {
  headline: string;
  total_responses: number;
  metrics: Metrics;
  approval_gate: ApprovalGate;
  run: RunMeta | null;
  coverage: { models: string[]; rows: CoverageRow[] };
  sentiment_by_model: SentimentRow[];
  sentiment_by_therapy: SentimentRow[];
  citation_counts: Record<string, number>;
  positioning: { order: string[]; rows: { model: string; counts: Record<string, number> }[] };
  alerts: AlertItem[];
}

export interface QuestionItem {
  question_id: string;
  version: number;
  persona: string;
  therapeutic_area: string;
  brand_focus: string;
  domain: string;
  question_text: string;
  approval_status: string;
  approver_name: string | null;
  approval_note: string | null;
  active: boolean;
  updated_at: string | null;
}

export interface QuestionsPayload {
  counts: { pending: number; approved: number; rejected: number; total: number };
  questions: QuestionItem[];
}

export interface ResponseDetail {
  response_id: string;
  question_id: string;
  llm_name: string;
  persona: string;
  therapeutic_area: string;
  status: string;
  finish_reason: string;
  response_text: string;
  block_reason: string | null;
  score: {
    sentiment_score: number;
    competitive_position: string;
    citation_status: string;
    scoring_rationale: string;
    brand_mentions: string[];
    key_claims: string[];
  } | null;
}

export interface AlertRecord {
  alert_id: string;
  score_id: string;
  response_id: string;
  rule_fired: string;
  severity: number;
  reason: string;
  created_at: string | null;
}

// --- Dashboard (Stage 2) --------------------------------------------------------------------- //
export interface DashTarget {
  target_id: string;
  display_name: string;
  kind: string; // "llm" | "synthesis" | "provider-api"
}

export interface DashKpis {
  responses_total: number;
  responses_captured: number;
  success_rate: number;
  scored: number;
  avg_sentiment: number;
  active_alerts: number;
  positioned: number;
  favourable: number;
  favourable_pct: number;
  last_run: {
    run_id: string;
    started_at: string | null;
    ended_at: string | null;
    responses_captured: number;
    questions_attempted: number;
    total_tokens: number;
  } | null;
}

export interface DashHeatCell {
  therapeutic_area: string;
  mean: number | null;
  count: number;
}

export interface DashRecentAlert {
  response_id: string;
  question_id: string;
  question_text: string;
  model: string;
  persona: string;
  alert_type: string;
  severity: number;
  sentiment: number | null;
  created_at: string;
  rules: { rule: string; severity: number; reason: string }[];
}

export interface Dashboard {
  filters: Record<string, string>;
  options: { personas: string[]; llms: string[]; therapeutic_areas: string[] };
  targets: DashTarget[];
  kpis: DashKpis;
  sentiment_histogram: { bucket_edges: number[]; series: { target_id: string; counts: number[] }[] };
  positioning: {
    order: string[];
    series: { target_id: string; counts: Record<string, number>; total: number }[];
  };
  heatmap: { therapeutic_areas: string[]; rows: { target_id: string; cells: DashHeatCell[] }[] };
  volume_by_week: { week: string; counts: Record<string, number> }[];
  recent_alerts: DashRecentAlert[];
}

export interface DashboardFilters {
  run_id?: string;
  persona?: string;
  therapeutic_area?: string;
  period?: string;
  llms?: string[];
}

export function getDashboard(f: DashboardFilters): Promise<Dashboard> {
  const p = new URLSearchParams();
  if (f.run_id) p.set("run_id", f.run_id);
  if (f.persona) p.set("persona", f.persona);
  if (f.therapeutic_area) p.set("therapeutic_area", f.therapeutic_area);
  if (f.period) p.set("period", f.period);
  (f.llms ?? []).forEach((l) => p.append("llm", l));
  return getJSON<Dashboard>(`/api/dashboard?${p.toString()}`);
}

// Configured targets with their config-sourced kind + display label — the single source of truth
// the frontend uses to label/classify any target by name (no hard-coded slug).
export interface TargetInfo {
  target_id: string;
  llm_name: string;
  display_name: string;
  kind: string;
  active: boolean;
}
export const getTargets = () => getJSON<TargetInfo[]>("/api/targets");

// --- Responses table (Stage 3) --------------------------------------------------------------- //
export interface ResponseRow {
  response_id: string;
  timestamp_utc: string;
  llm_name: string;
  persona: string;
  therapeutic_area: string;
  domain: string;
  status: string;
  question_id: string;
  question_text: string;
  sentiment: number | null;
  competitive_position: string | null;
  citation_status: string | null;
  has_alert: boolean;
}
export interface ResponsesTable {
  items: ResponseRow[];
  total: number;
  page: number;
  page_size: number;
}
export interface ResponsesQuery {
  run_id?: string;
  persona?: string;
  status?: string;
  therapeutic_area?: string;
  period?: string;
  llms?: string[];
  search?: string;
  page?: number;
  page_size?: number;
}
function responsesParams(q: ResponsesQuery): URLSearchParams {
  const p = new URLSearchParams();
  if (q.run_id) p.set("run_id", q.run_id);
  if (q.persona) p.set("persona", q.persona);
  if (q.status) p.set("status", q.status);
  if (q.therapeutic_area) p.set("therapeutic_area", q.therapeutic_area);
  if (q.period) p.set("period", q.period);
  if (q.search) p.set("search", q.search);
  if (q.page) p.set("page", String(q.page));
  if (q.page_size) p.set("page_size", String(q.page_size));
  (q.llms ?? []).forEach((l) => p.append("llm", l));
  return p;
}
export const getResponsesTable = (q: ResponsesQuery) =>
  getJSON<ResponsesTable>(`/api/responses?${responsesParams(q).toString()}`);

// CSV export reuses the existing /reports/export endpoint (period → date_from; single LLM only).
export function exportUrl(q: ResponsesQuery, format: "csv" | "json" = "csv"): string {
  const p = new URLSearchParams();
  p.set("format", format);
  if (q.run_id) p.set("run_id", q.run_id);
  if (q.persona) p.set("persona", q.persona);
  if (q.status) p.set("status", q.status);
  if (q.therapeutic_area) p.set("therapeutic_area", q.therapeutic_area);
  if (q.llms && q.llms.length === 1) p.set("llm", q.llms[0]);
  if (q.period === "7d" || q.period === "30d") {
    const days = q.period === "7d" ? 7 : 30;
    p.set("date_from", new Date(Date.now() - days * 864e5).toISOString());
  }
  return `/reports/export?${p.toString()}`;
}

// --- Alerts feed (Stage 3) -------------------------------------------------------------------- //
export interface AlertFeedItem {
  alert_id: string;
  response_id: string;
  question_id: string;
  question_text: string;
  model: string;
  persona: string;
  therapeutic_area: string;
  rule: string;
  alert_type: string;
  severity: number;
  reason: string;
  sentiment: number | null;
  created_at: string;
}
export interface AlertsFeed {
  counts_by_rule: Record<string, number>;
  counts_by_type: Record<string, number>;
  total: number;
  page: number;
  page_size: number;
  items: AlertFeedItem[];
}
export interface AlertsQuery {
  rule?: string;
  persona?: string;
  llm?: string;
  severity?: number;
  period?: string;
  page?: number;
  page_size?: number;
}
export function getAlertsFeed(q: AlertsQuery): Promise<AlertsFeed> {
  const p = new URLSearchParams();
  if (q.rule) p.set("rule", q.rule);
  if (q.persona) p.set("persona", q.persona);
  if (q.llm) p.set("llm", q.llm);
  if (q.severity != null) p.set("severity", String(q.severity));
  if (q.period) p.set("period", q.period);
  if (q.page) p.set("page", String(q.page));
  if (q.page_size) p.set("page_size", String(q.page_size));
  return getJSON<AlertsFeed>(`/api/alerts?${p.toString()}`);
}

// --- LLM Comparison (Stage 3) ----------------------------------------------------------------- //
export interface ComparisonColumn {
  response_id: string;
  llm_name: string;
  status: string;
  finish_reason: string;
  response_text: string;
  block_reason: string | null;
  sentiment: number | null;
  competitive_position: string | null;
  citation_status: string | null;
  scoring_rationale: string | null;
}
export interface Comparison {
  question_id: string;
  question_text: string;
  persona: string;
  run_id: string;
  columns: ComparisonColumn[];
}
export const getComparison = (questionId: string, runId: string) =>
  getJSON<Comparison>(
    `/api/comparison?question_id=${encodeURIComponent(questionId)}&run_id=${encodeURIComponent(runId)}`,
  );

async function getJSON<T>(url: string): Promise<T> {
  const resp = await fetch(url, { headers: { Accept: "application/json" } });
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  return (await resp.json()) as T;
}

export const getRuns = () => getJSON<RunSummary[]>("/api/runs");
export const getReport = (runId: string) =>
  getJSON<Report>(`/api/runs/${encodeURIComponent(runId)}/report`);
export const getResponse = (responseId: string) =>
  getJSON<ResponseDetail>(`/api/responses/${encodeURIComponent(responseId)}`);
// Alerts ordered by severity (WRONG_INDICATION first); reuses the existing read-only endpoint.
export const getAlerts = () => getJSON<AlertRecord[]>("/reports/alerts");

export function getQuestions(status: string, persona?: string): Promise<QuestionsPayload> {
  const params = new URLSearchParams({ status });
  if (persona) params.set("persona", persona);
  return getJSON<QuestionsPayload>(`/api/questions?${params.toString()}`);
}

// --- writes: reuse the existing approval endpoints (audit-logged server-side) ---------------- //
async function postJSON(url: string, body: unknown): Promise<void> {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    let detail = `${resp.status}`;
    try {
      const e = await resp.json();
      detail = e.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
}

export const approveQuestion = (id: string, approverName: string) =>
  postJSON(`/approvals/questions/${encodeURIComponent(id)}/approve`, { approver_name: approverName });

export const rejectQuestion = (id: string, approverName: string, reason: string) =>
  postJSON(`/approvals/questions/${encodeURIComponent(id)}/reject`, {
    approver_name: approverName,
    reason,
  });

// Edit reuses the EXISTING edit endpoint (creates a new version server-side; audited). Only the
// supplied fields change. Not a new write path — the approval gate is untouched.
export interface QuestionEdit {
  question_text?: string;
  persona?: string;
  therapeutic_area?: string;
  brand_focus?: string;
  domain?: string;
  active?: boolean;
}
export const editQuestion = (id: string, changes: QuestionEdit) =>
  postJSON(`/approvals/questions/${encodeURIComponent(id)}/edit`, changes);
