# Contract — REST API (FastAPI, local-only)

`api.py`. **Reports are read-only.** The only writes are local Medical Affairs **Approvals**. The
system never exposes an endpoint that submits to an external LLM or takes outward action
(Principle I). All endpoints are local-only for the POC (no auth — out of scope).

## Health

### `GET /health`
Runs the startup credential preflight (present + reachable) and returns target status.
- **200**: `{ "status": "ok", "targets": [{ "target_id": "openai-gpt4o", "reachable": true }, ...] }`
- **503**: `{ "status": "degraded", "missing": ["GOOGLE_API_KEY"], "unreachable": [] }`

## Reports (read-only)

### `GET /reports/responses`
Filtered, paginated response query (FR-012).
- **Query params**: `llm`, `persona`, `therapeutic_area`, `brand`, `domain`, `date_from`,
  `date_to`, `sentiment_min`, `sentiment_max`, `alert_status`, `status`, `page`, `page_size`.
- **200**: `{ "items": [ResponseView], "page": 1, "page_size": 50, "total": 1234 }`
  where `ResponseView` includes response fields + latest `ScoringRecord` summary + `alert` flags.

### `GET /reports/responses/{response_id}`
- **200**: full response text + all scoring versions + alerts (dashboard drill-down, FR-024).
- **404**: unknown id.

### `GET /reports/runs/{run_id}/summary`
- **200**: run summary (FR-026): `run_id`, start/end, attempted, captured-by-status, alert_count,
  total_tokens, est_cost.

### `GET /reports/export?format=csv|json`
Exports the current filter set (FR-025). **200** with `text/csv` or `application/json`.

### `GET /reports/alerts`
- **200**: alert list ordered by severity (WRONG_INDICATION first).

## Approvals (read-write, local Medical Affairs)

### `GET /approvals/questions?status=PENDING`
- **200**: list of questions by approval status / persona / therapeutic area.

### `POST /approvals/questions/{question_id}/approve`
- **Body**: `{ "approver_name": "string" }`
- **200**: question now `APPROVED` (approver recorded), eligible for next run.
- **409**: question is `REJECTED` (terminal).

### `POST /approvals/questions/{question_id}/reject`
- **Body**: `{ "approver_name": "string", "reason": "string" }`
- **200**: question now `REJECTED`, excluded from all runs.

### `POST /approvals/questions/{question_id}/edit`
- **Body**: partial question fields.
- **200**: creates a **new version** (no hard delete, FR-001); returns new version number.

**Invariant**: No endpoint submits a question to any LLM. Submission happens only inside scheduled
or CLI-triggered runs over `APPROVED` questions.
