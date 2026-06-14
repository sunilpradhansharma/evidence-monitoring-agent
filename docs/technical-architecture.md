# Technical Architecture — Evidence Monitoring Agent (POC)

This document describes how the POC is built. It draws on the SRS (`docs/SRS.pdf`), the
specification set (`specs/001-evidence-monitoring-poc/`), the constitution
(`.specify/memory/constitution.md`), and the diagrams in `docs/diagrams/`.

## 1. Overview

The Evidence Monitoring Agent runs a daily, unattended job: it takes a curated bank of
**human-approved** questions, asks them to several public LLMs, stores every answer as an
**immutable** record, **scores** each answer with Claude, raises **deterministic** alerts on
concerning answers, and presents the result on a self-contained dashboard. It is **local-first**
and designed so every external dependency can be swapped for an AWS service without rewriting core
logic.

### Diagram index

| Diagram (`docs/diagrams/`) | Purpose |
|---|---|
| `evidence_monitor_system_context.svg` | Actors, the agent, and the external LLM targets. |
| `evidence_monitor_detailed_pipeline.svg` | Full pipeline: approved question → response → score → alert → dashboard. |
| `evidence_monitor_module_architecture` *(planned)* | Module/package map and the two seams. |
| `orchestrator_detailed_langgraph_graph.svg` | The explicit LangGraph node graph. |
| `per_question_dispatch_four_outcomes.svg` | Per-question dispatch; the four capture outcomes. |
| `detailed_daily_run_sequence.svg` | The daily run as a step-by-step sequence. |
| `scoring_and_alert_decision_flow.svg` | Score → deterministic alert decision. |
| `evidence_monitor_detailed_erd.html` | The data model (entities + relationships). |
| `evidence_monitor_local_execution_view.svg` | How everything runs on one local machine. |

## 2. Key invariants

These hold at all times and are enforced in code (and checked by the `constitution-guardian` and
`content-agnostic-auditor` subagents):

- **Only APPROVED questions are submitted.** Eligibility is `approval_status == APPROVED && active`.
- **Responses are write-once.** The Response repository raises on any update attempt.
- **Scores never mutate responses.** A score is a separate, versioned `Scoring_Record` linked by
  `response_id`; re-scoring adds a version.
- **Question counts are version-aware.** Questions are versioned (edits/approvals append a new
  version, never overwrite); every count and list uses the **latest version per `question_id`**, so
  a question is counted once regardless of its edit history (ADR-0009).
- **Alerts are decided by code, never by the model.**
- **Model ids, parameters, rate limits, thresholds, cron, and token budget come from config.**
- **Brand/competitor/indication names appear only in the question bank and config — never in code.**
- **No PII/PHI is stored anywhere; secrets are never logged.**
- **The audit log is append-only.**
- **A run is resumable** from the last completed question without re-submission.

## 3. Architecture Decision Records (ADR index)

Full records in [`docs/adr/`](adr/):

| ADR | Decision |
|-----|----------|
| [0001](adr/0001-spec-driven-development.md) | Spec-driven development with GitHub Spec Kit |
| [0002](adr/0002-local-first-with-production-swap.md) | Local-first POC with production swap behind seams |
| [0003](adr/0003-llm-scores-code-decides.md) | LLM scores; deterministic code decides alerts |
| [0004](adr/0004-immutable-responses-versioned-scores.md) | Immutable responses + versioned scoring records |
| [0005](adr/0005-combined-local-ui.md) | Combined Reports + Approvals UI, local-only, approver-name, no RBAC *(UI-rendering portion superseded by ADR-0008)* |
| [0006](adr/0006-citation-status-wrong-indication.md) | `citation_status` with `WRONG_INDICATION` + highest-severity alert |
| [0007](adr/0007-offline-e2e-capture-rate-and-cli-preflight.md) | Offline e2e capture-rate gate + CLI credential preflight |
| [0008](adr/0008-react-spa-over-fastapi-readonly-api.md) | React SPA primary UI, served by FastAPI over a read-only `/api` layer reusing `render.py` |
| [0009](adr/0009-version-aware-question-counts.md) | Version-aware question counts (latest version per `question_id`) |
| [0010](adr/0010-gemini-thinking-disabled.md) | Disable Gemini "thinking" + pin a current model id (config + adapter) |
| [0011](adr/0011-provider-evidence-dev-target.md) | Labeled PubMed+Claude "Provider evidence (dev)" stand-in — explicitly NOT Open Evidence |

## 4. Module / package map

```text
src/evidence_monitor/
├── config/         settings.py (env: model ids, paths, thresholds, cron, token budget)
│                   targets.yaml (targets, model versions, params, rate limits, personas, ToS ack)
├── data_access/    interface.py (DataAccess + Repository protocols)  ← the storage seam
│                   sqlite_store.py, queries.py (filtered/paginated reads), audit.py (append-only)
├── llm/            client.py (Claude orchestrator + scorer; model id from config)  ← the LLM seam
│                   adapters/ base.py (retry/backoff, rate limit, mock), openai_gpt4o.py,
│                            gemini.py (safety→BLOCKED), claude_target.py, open_evidence.py,
│                            provider_evidence_dev.py (PubMed + Claude synthesis dev stand-in)
│                   registry.py (config→adapter wiring + persona/active gating)
├── question_repo/  repository.py (CRUD + versioning), approval.py (gate), importer.py (CSV/Excel), seed.py
├── response_repo/  repository.py (immutable writes), schema.py (Response record)
├── scoring/        scorer.py (structured JSON), prompts.py (MA-reviewed prompt)
├── alerts/         rules.py (4 deterministic rules incl. wrong-indication)
├── orchestrator/   state.py, nodes.py, graph.py (LangGraph), run_manager.py (run_id, resume, checkpoint)
├── dashboard/      render.py (aggregation → legacy HTML + self-contained export + CSV/JSON),
│                   json_api.py (read-only JSON serializers reusing render.py — no new aggregation),
│                   template.html / reports_section.html / _styles.html (legacy server-rendered UI)
├── observability/  logging.py (structured JSON + secret redaction), cost.py (tokens + $)
├── scheduler.py    cron / APScheduler entry
├── cli.py          import-questions / run / subset / dry-run / health-check / approve / reject
│                   (+ test helpers: approve-all-test-numbered, reset-to-pending)
└── api.py          FastAPI: React SPA at "/", read-only /api/* JSON, /reports/* JSON + export,
                    read-write /approvals/* (the only writes), /health, legacy HTML at /html

frontend/           React + TypeScript SPA (Vite, Tailwind, Recharts, Figtree via @fontsource).
                    Builds to frontend/dist/ (git-ignored); FastAPI serves it at "/".
```

> **UI note.** The **primary UI is a React single-page app** (ADR-0008) served by FastAPI from the
> built static files at `http://127.0.0.1:8000`. It reads the read-only `/api/*` endpoints and
> writes only via the existing `/approvals/*` POSTs. The original server-rendered (Jinja) UI is
> retained at `/html`; when no frontend build is present, `/` falls back to it. The pipeline
> diagrams below predate the React rewrite and depict the dashboard generically — the capture →
> score → alert pipeline they show is unchanged.

## 5. The `data_access` seam

All persistence goes through protocols in `data_access/interface.py`
([contract](../specs/001-evidence-monitoring-poc/contracts/data-access.md)) —
`QuestionRepository`, `ResponseRepository`, `ScoringRepository`, `AlertRepository`,
`RunRepository`, and the `AuditWriter`. Core modules depend only on these protocols, so the
SQLite implementation can be replaced by an Aurora/DynamoDB one without touching business logic.
The seam is where immutability, versioning, append-only audit, and soft-delete/retention are
**enforced**, not merely encouraged.

## 5a. Web layer — React SPA + FastAPI + read-only `/api` (ADR-0008)

One FastAPI app (`api.py`) is the whole web layer; there is no separate backend service.

- **React SPA (primary UI).** `frontend/` is a Vite + TypeScript + Tailwind app (Recharts for the
  sentiment chart, Figtree base font via `@fontsource/figtree`). `npm run build` emits static files to
  `frontend/dist/`. FastAPI serves them: hashed assets at `/assets`, and `index.html` at `/` and as
  the fallback for unknown client-side routes (registered **last** so it never shadows an API/HTML
  route). With no build present, `/` serves the legacy HTML instead, so the suite and a fresh
  checkout still work without Node.
- **Read-only `/api` layer.** `dashboard/json_api.py` serializes exactly what `render.py` already
  computes — **no new aggregation**:
  - `GET /api/runs` — runs for the selector (id, timestamps, captured/fail counts).
  - `GET /api/runs/{run_id}/report` — the full Reports payload for one run: headline, run metrics
    (responses/success/truncated/failed/blocked, capture rate vs ≥95%, alerts + by-type, scope,
    cost, tokens, duration), the question × model coverage matrix (per-cell status class, label,
    `truncated`, `response_id`), sentiment-by-model and -therapy, citation counts, the positioning
    table, and the alerts list. Counts are version-aware and run-scoped exactly as the HTML view.
  - `GET /api/questions?status=&persona=` — version-aware questions (latest per `question_id`) plus
    global status counts (pending/approved/rejected/total).
  - `GET /api/responses/{response_id}` — full response text + scoring rationale for click-through.
- **Legacy/JSON Reports endpoints retained.** `GET /reports/responses`, `/reports/responses/{id}`,
  `/reports/alerts`, `/reports/export` (CSV/JSON), `/reports/runs/{id}/summary`, and the legacy HTML
  at `/html`.
- **The only writes** remain `POST /approvals/questions/{id}/approve|reject|edit` — audit-logged,
  through the question-repo approval seam. The SPA calls these directly; no write path was added.
  (`POST /score-review/{id}` exists but is disabled in this build and returns 404.)
- **Data flow (read).** SPA → `GET /api/runs` (default to latest) → `GET /api/runs/{id}/report` →
  render; a coverage cell or alert opens `GET /api/responses/{id}` in a side panel. **Data flow
  (write).** Approvals tab → `POST /approvals/.../approve|reject` (reviewer name required) → the
  approval seam writes a new question version + an audit entry → the SPA re-fetches `/api/questions`.

## 6. Data model

Mirrors `docs/diagrams/evidence_monitor_detailed_erd.html` and
[`data-model.md`](../specs/001-evidence-monitoring-poc/data-model.md). No entity contains PII/PHI.

| Entity | Role | Key fields | Relationships |
|--------|------|-----------|---------------|
| **Question** | curated, versioned, approved item | `question_id`, `version`, `persona`, `therapeutic_area`, `brand_focus`, `domain`, `active`, `approval_status`, `approver_name` | 1→* Response |
| **LLM_Target** | a configured public model | `target_id`, `llm_name`, `model_version`, params, `rpm/tpm_limit`, `personas`, `tos_acknowledged` | 1→* Response |
| **Run** | a scheduled/ad-hoc batch | `run_id`, `trigger_type`, timings, counts, tokens, cost, `last_completed_question_id` | 1→* Response, AuditLog |
| **Response** *(immutable)* | one target's answer to one question | `response_id`, FKs, `response_text` (full), `status` (SUCCESS/FAILED/TRUNCATED/BLOCKED), `finish_reason`, `block_reason` | *→1 Question/Target/Run |
| **Scoring_Record** *(versioned)* | derived score for a response | `score_id`, `response_id`, `version`, `sentiment_score`, `competitive_position`, **`citation_status`**, `brand_mentions`, `key_claims`, `scoring_rationale`, `scorer_model` | *→1 Response |
| **Alert** | a triggered flag | `alert_id`, `score_id`, `response_id`, `rule_fired`, `severity`, `reason` | *→1 Scoring_Record |
| **Audit_Log** *(append-only)* | every external query/response | `audit_id`, `run_id`, `event_type`, `role`, `ts`, `http_status`, `detail` | *→1 Run |

## 7. LangGraph orchestration

The run is an explicit, code-defined graph (`orchestrator/graph.py`) — **no autonomous loops**.
Nodes: **load** approved questions → **dispatch** to each target → **persist** the immutable
response → **score** → **evaluate alerts** → **summarize**. `RunState` carries progress;
`run_manager.py` assigns the `run_id`, checkpoints after every persist, and resumes from
`last_completed_question_id`. This makes the flow inspectable, checkpointable, and a clean match
for AWS Step Functions in production. See `orchestrator_detailed_langgraph_graph.svg`.

## 8. LLM integration

Every target implements the adapter protocol in `llm/adapters/base.py`
([contract](../specs/001-evidence-monitoring-poc/contracts/llm-adapter.md)):

- **Retry/backoff** — transient failures (timeout, 429, 5xx) retry with exponential backoff
  (default 3 attempts: 2s/4s/8s). After the budget, the record is `FAILED` and the run continues.
- **Rate limiting** — per-target `rpm`/`tpm` limits from config.
- **Status mapping** — length cap → `TRUNCATED`; safety/filter block → `BLOCKED` (distinct from
  `FAILED`, important for Gemini).
- **Provider quirks live in the adapter.** Gemini is a *thinking* model whose hidden reasoning
  tokens count against `max_output_tokens`; the adapter sets `thinking_budget=0` so the whole budget
  goes to the visible answer (with a modest `max_tokens` bump in config), which we score. This is a
  config + adapter concern only — core logic is untouched (ADR-0010).
- **Offline/mock mode** — deterministic canned results with no network call, so e2e and
  capture-rate tests are fast and repeatable.
- **Config-sourced** — model ids/params/endpoints are never hard-coded. Adding a target is a new
  adapter + a `targets.yaml` entry, with no change to orchestration.

Claude plays two roles through `llm/client.py`: the **orchestrator** and the **scorer**. The
monitored Claude *target* is a separate adapter queried as an end-user; calls are tagged
`ORCHESTRATOR` vs `TARGET` in the audit log.

**Active targets (from `config/targets.yaml`):** `openai-gpt4o` → `gpt-4o-2024-08-06`,
`google-gemini` → `gemini-2.5-flash`, `anthropic-claude-target` → `claude-sonnet-4-6`, and the
Provider-only dev stand-in `provider-evidence-dev` (`active: true` in the committed config). The real
`open-evidence` target is present but `active: false`.

### The adapter seam — worked example: `provider-evidence-dev`

Adding a target is a new adapter class + a `targets.yaml` entry + a registry mapping — the
orchestrator never changes. `provider-evidence-dev` (ADR-0011) is the worked example. It is a
**development stand-in** for the future Open Evidence Provider target — explicitly **NOT Open
Evidence** and never reported as such — and it shows the seam handling a *composite* provider:

1. Its `_call_live` queries public **PubMed E-utilities** (`esearch` → `efetch`) for the question
   (NCBI `tool`/`email` from config; optional `api_key`), then
2. calls the existing **Claude client** (orchestrator role) to synthesize a cited answer **from the
   retrieved abstracts only**.

The synthesized text plus a provenance footer (the PubMed query + the PMIDs used) is the captured
response — recorded immutably and scored by the normal pipeline. It inherits the base adapter's
retry/backoff and offline-mock behaviour, and a PubMed outage degrades to `FAILED` so the run
continues. It is Provider-persona only and gated by the same `active`/persona rule as every target.

**Where the real Open Evidence adapter slots in:** a future `open_evidence.py` adapter implementing
the same protocol (their `createAnalysisStreaming` API — needs API key + org id + signed BAA + Legal/
ToS sign-off) drops into this seam; activating it (and retiring/deactivating the dev stand-in) is a
config + adapter change, no core change. Its credentials already have config slots
(`OPENEVIDENCE_API_KEY`, `OPENEVIDENCE_ORG_ID`), required only when that target is `active`.

## 9. Scoring + the four alert rules

The scorer (`scoring/scorer.py`) returns a JSON object validated against
[`scoring-output.schema.json`](../specs/001-evidence-monitoring-poc/contracts/scoring-output.schema.json):
`sentiment_score (−1..+1)`, `competitive_position`, `citation_status`, `brand_mentions`,
`key_claims (≤5)`, `scoring_rationale`. The result is stored as a new `Scoring_Record` version.

`alerts/rules.py` then applies **deterministic** rules (see `scoring_and_alert_decision_flow.svg`):

1. `sentiment_score` < negative threshold (default **−0.3**).
2. `competitive_position` == `NOT_RECOMMENDED`.
3. competitor brand sentiment ≥ **0.3** higher than our therapy in the same response.
4. `citation_status` == `WRONG_INDICATION` → **highest severity**.

## 10. Explainability

No score is presented without its evidence: every `Scoring_Record` carries the **brands detected**,
**up to five key claims**, and a **rationale**. This lets Medical Affairs judge each score rather
than trust it blindly (Constitution VII).

## 11. Security & privacy

- No PII/PHI in any entity, fixture, log, or comment; questions are generic.
- Brand/competitor/indication strings only in `data/question_bank.csv` and config.
- Secrets come from env/`.env` (denied to tooling); the logging layer **redacts** secret-shaped
  strings; nothing is forwarded to third parties.
- A **startup preflight** validates that required credentials are present and reachable and exits
  with a clear, non-secret error before any question is submitted.

## 12. Testing strategy

- **Unit** — schemas, repositories, adapters (mock), alert rules, redaction, cost.
- **Component** — approval gate, orchestrator nodes, queries, scoring versioning, APIs.
- **E2E** — a full mock run over the seed bank (`tests/e2e/`): captures every (APPROVED question ×
  eligible target), asserts **≥95% capture** (including a flaky-target case that still clears the
  bar), scores + alerts, resumes without duplicates, and produces the self-contained dashboard plus
  CSV/JSON exports.
- **Gates** — ≥70% coverage on core modules; the capture-rate and scoring schema are asserted by
  automated tests; `ruff` format/lint via a PostToolUse hook. (Constitution XI.)

## 13. Config & runtime

- `config/settings.py` — env-sourced model ids, paths, alert thresholds/weights, cron schedule,
  token budget; runs the credential preflight.
- `config/targets.yaml` — targets, model versions, parameters, rate limits, personas served, ToS
  acknowledgment.
- Entry points: `cli.py` (`import-questions` / `run` / `subset` / `dry-run` / `health-check` /
  `approve` / `reject`, plus the test helpers `approve-all-test-numbered` / `reset-to-pending`; a
  live `run`/`subset` runs the credential preflight first), `scheduler.py` (daily cron), `api.py`
  (the React SPA at `/`, read-only `/api/*` and `/reports/*`, read-write `/approvals/*`, `/health`,
  and the legacy HTML at `/html`).
- Frontend build: `cd frontend && npm install && npm run build` produces `frontend/dist/`, which
  `api.py` serves at `/`. For development, `npm run dev` runs a Vite server that proxies `/api`,
  `/approvals`, and `/health` to the FastAPI backend.

## 14. POC → production

The seams make production a configuration/implementation swap, not a rewrite (Constitution X):

| Concern | POC (local) | Production (AWS) | Swap point |
|---------|-------------|------------------|------------|
| Storage | SQLite / DuckDB | **Aurora** (relational) + **DynamoDB** (audit) | `data_access/interface.py` |
| Claude (orchestrator + scorer) | Anthropic API | **Amazon Bedrock** | `llm/client.py` + config |
| Scheduling | APScheduler / cron | **Amazon EventBridge Scheduler** | `scheduler.py` |
| Orchestration runtime | local process | **Fargate** + **Step Functions** | deployment + `run_manager` |
| Dashboard / exports | React SPA + `/api` served by FastAPI; CSV/JSON via `/reports/export` | **Amazon S3 / CloudFront** (static SPA) + the API behind ALB/Fargate | `frontend/` build + `api.py` |
| Logs / metrics | structured JSON files | **CloudWatch** | `observability/logging.py` |
| Secrets | env / `.env` | **AWS Secrets Manager** | `config/settings.py` |
