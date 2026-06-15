// Typed client for the read-only JSON API (/api/*) and the existing approval write endpoints.
// Writes reuse the SAME POST endpoints the server-rendered UI uses — no new write paths.

export interface RunSummary {
  run_id: string;
  trigger_type: string;
  started_at: string | null;
  ended_at: string | null;
  responses_captured: number;
  failure_count: number;
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
  domain: string;
  question_text: string;
  approval_status: string;
  approver_name: string | null;
  approval_note: string | null;
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
