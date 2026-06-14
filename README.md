# Evidence Monitoring Agent

A local, spec-driven proof-of-concept that monitors how public large language models (LLMs)
represent AbbVie therapies versus competitors when asked realistic prospect, patient, and
provider questions. It **only captures and scores** — it never gives medical advice, contacts
anyone, or takes any outward action — and a **human approves every question before it is ever
submitted** to an LLM. The output is a queryable record of what each model said, an explainable
score for each response, threshold-based alerts on concerning answers, and a simple dashboard for
Medical Affairs and Commercial.

## Status

**Design complete · build in progress.** This project is **spec-first**: the specification,
plan, data model, and task breakdown were written and reviewed before any application code. It
**runs locally** — Claude (via the Anthropic API) acts as both the orchestrator and the scorer,
with all model ids sourced from config. Amazon Bedrock is the documented production swap.

➡️ Living status, phase roadmap, and decisions log: **[docs/project-status.md](docs/project-status.md)**

## Capabilities

- **Question Repository (approval gate)** — a versioned bank of generic, no-PII questions.
  Medical Affairs moves each question `PENDING → APPROVED → REJECTED`; only **APPROVED** questions
  are ever submitted.
- **LLM Response Agent** — a scheduled, unattended run that submits every approved question to
  every configured target, retries transient failures, and records every answer.
- **Immutable Response Repository** — every response is stored once, full text unedited, with a
  status of `SUCCESS / FAILED / TRUNCATED / BLOCKED` and full metadata; records are queryable.
- **Scoring + Alerts** — Claude produces a structured score per response; deterministic code
  decides which responses raise an alert.
- **Combined Reports + Approvals UI** — one local-only app: read-only Reports for stakeholders and
  read-write Approvals for Medical Affairs.
- **Scheduling + Audit** — a daily run on a cron/scheduler, plus an append-only audit log of every
  query and response for compliance.

## Scope

**In scope (POC):**
- The **4 core components**: Question Repository, LLM Response Agent, Response Repository, Scoring
  & Alerting.
- **3 public LLMs** — OpenAI GPT-4o, Google Gemini, and Anthropic Claude (queried as an end-user)
  — **plus a conditional Open Evidence** target used only for Provider-persona questions and only
  if API access is confirmed.
- The **162-question bank** (Patient 59 · Prospect 49 · Provider 54; across Immunology,
  Neuroscience, and Oncology).
- **Local execution** — SQLite/DuckDB storage, a self-contained HTML dashboard, no cloud services.

**Out of scope (POC):** any private/internal model; production data-platform integrations (Veeva,
Salesforce, data lake); real-time notification pipelines; user auth / RBAC / multi-tenant; mobile
apps. The broader **GEO / multi-agent / literature-mining / pharmacovigilance** vision is **future
direction, not POC scope**.

## The Constitution (11 principles)

The project is governed by [`.specify/memory/constitution.md`](.specify/memory/constitution.md).
In brief:

1. **Human approves, system suggests** — only APPROVED questions are submitted; scores/alerts are advisory.
2. **Immutable & auditable** — responses are write-once; scores are a separate versioned record; every call is audit-logged.
3. **No PII/PHI** — questions are generic; no personal data is stored anywhere.
4. **Content-agnostic code** — drug/competitor/indication names live only in the question bank and config, never in code.
5. **Config-driven targets** — adding/removing an LLM is a config + adapter change; model ids are never hard-coded.
6. **Terms of service & data residency** — comply with each provider's ToS; store responses only in local, controlled storage.
7. **Explain the score** — every score carries detected brands, up to five key claims, and a rationale.
8. **LLM scores, code decides** — Claude produces the score; deterministic code decides alerts.
9. **Resilient & resumable** — retry with backoff, mark FAILED after the budget, resume from the last completed question; target ≥95% capture.
10. **Built to grow into production** — externals sit behind clean `llm` and `data_access` seams that swap to Bedrock/Aurora by config.
11. **Quality is testable** — unit/component/e2e tests; ≥70% coverage on core; capture-rate and scoring schema are checked automatically.

## Architecture diagrams

All diagrams live in [`docs/diagrams/`](docs/diagrams/). Each one below is followed by a plain-language,
step-by-step walkthrough so a non-engineer can follow the flow.

### 1. System context

Shows where the whole system sits — who uses it, where it runs, and which external LLM services it talks to.

![System context](docs/diagrams/evidence_monitor_system_context.svg)

1. Everything inside **"Your local machine"** is the POC; everything under **"External LLM services (internet)"** lives outside it, reached over HTTPS.
2. A **local scheduler** (cron, daily at 02:00) kicks off a **run** of the **Evidence Monitoring Agent** (the local Python POC).
3. **Medical Affairs** sits on the left and feeds the agent by **curating + approving** questions — nothing runs against an unapproved question.
4. The agent submits approved questions to the external targets — **OpenAI GPT-4o**, **Google Gemini**, **Anthropic Claude** (used here as a *target*, not the orchestrator), and the conditional **Open Evidence** (Provider-persona only).
5. Each target answers over **HTTPS (query ↔ response)**; the agent captures what comes back.
6. The agent produces a **Dashboard (HTML) + CSV/JSON export**, which **Stakeholders (Commercial + MA)** read as **findings**.

### 2. Detailed end-to-end pipeline

Answers "what happens to one approved question, from input config all the way to a dashboarded, alerted result?"

![Detailed end-to-end pipeline](docs/diagrams/evidence_monitor_detailed_pipeline.svg)

1. **Inputs** feed the run: `config.yaml` (targets, limits, params), `.env` secrets (API keys), and the question CSV (Medical Affairs curation).
2. Those load the **Question repository** — versioned, with the `PENDING → APPROVED` gate.
3. The **Orchestrator (Claude)** pulls only **APPROVED** questions and assigns a `run_id`.
4. A **per-question fan-out** sends each question to the **4 adapters**, rate-limited, retrying transient failures up to 3 times.
5. Every answer lands in the **Response repository** — immutable, with full metadata, retained 24 months.
6. **Scoring (Claude)** turns each stored response into structured JSON (sentiment, competitive position, claims).
7. The **Alert engine** applies deterministic rules, then **Dashboard + export** renders the four sections, CSV/JSON, and the run summary.
8. Running alongside the whole pipeline, **Observability** captures the **append-only audit log**, **structured JSON logs**, and **cost tracking** (tokens, $) — every stage writes here.

### 3. LangGraph orchestration state graph

Answers "what are the explicit, code-defined steps of a run — and how does it resume after an interruption?"

![LangGraph orchestration state graph](docs/diagrams/orchestrator_detailed_langgraph_graph.svg)

1. The run begins at **START** and enters **`init_run`**, which sets the `run_id`, loads config, and figures out any resume point.
2. **`load_questions`** pulls the questions whose `status = APPROVED`.
3. **`dispatch + collect`** submits each question to each target (retry ≤ 3); the loop arrow (↻) shows it repeats per question × target.
4. **`persist + checkpoint`** writes each answer immutably and saves a cursor (the resume point).
5. The **"more questions?"** decision loops back to dispatch (**yes → next question**) until there are none left (**no**).
6. Then **`score_batch`** runs Claude for structured JSON, **`evaluate_alerts`** applies the deterministic rules, and **`render + summary`** produces HTML/export/cost and notifies, ending at **END**.
7. The side panel **RunState** (`run_id`, trigger, targets, APPROVED questions, the resume **cursor**, responses, scores, alerts, summary) is the shared state every node reads and updates — the saved cursor is what makes a run resumable.

### 4. Per-question dispatch (four outcomes)

Answers "for a single question sent to a single target, how do we decide whether it's SUCCESS, TRUNCATED, BLOCKED, or FAILED?"

![Per-question dispatch — four outcomes](docs/diagrams/per_question_dispatch_four_outcomes.svg)

1. **Pull question**, then **Submit to target** (rate-limited) and inspect the **`finish_reason`** the target returns.
2. **`ok`** → store the record as **SUCCESS**.
3. **`length`** (the answer hit the token ceiling) → **bump `max_tokens` and retry once**; if still cut off, store as **TRUNCATED** with the full captured text preserved.
4. **`safety`** (the provider's filter blocked it) → store as **BLOCKED**, with the block reason — kept distinct from a failure.
5. **`error`** → **retry ≤ 3** with exponential backoff (**2s · 4s · 8s**); if the budget is exhausted, store as **FAILED**.
6. Whatever the outcome, the flow moves to **Next** and continues; the **↻ resumable** marker shows the run can pick up here after an interruption without re-sending completed work.

### 5. Daily-run sequence (who calls whom)

Answers "in time order, which component calls which during a daily run?"

![Daily-run sequence](docs/diagrams/detailed_daily_run_sequence.svg)

1. The **daily run** starts the **Orchestrator (Claude)**, which first loads config + secrets.
2. The orchestrator asks the **Question repository** to **fetch approved**, and gets back the **question batch**.
3. It then enters a **loop · per question × target**, submitting each to the **LLM targets** (3 public LLMs) with **retry ≤ 3**, receiving a **response / error**.
4. Each result is handed to the **Response repository** to **persist (status)**, which returns a **`response_id`** and writes an **audit** entry.
5. After capture, the orchestrator calls **Scoring + alerts (Claude)** to **score batch**, gets **Claude JSON** back, and the code attaches the **score + alert flag**; **alerts ready** signals completion.
6. Finally the orchestrator **renders the dashboard + run summary + audit** — the run's visible output.

### 6. Scoring & alert decision flow

Answers "how does one stored response become a structured score, and how does code (not the model) decide whether to alert?"

![Scoring and alert decision flow](docs/diagrams/scoring_and_alert_decision_flow.svg)

1. Start from a **Response record** (its full `response_text`) and the **MA-reviewed scoring prompt** template.
2. **Claude scoring** (Bedrock / API) reads both and returns **structured JSON**: `sentiment_score` (−1..+1), `competitive_position`, `citation_status` (including **WRONG_INDICATION** for wrong-disease content), `brand_mentions[]`, up to five `key_claims`, and a `scoring_rationale`.
3. That score is saved as a **scoring record** — versioned and linked to the `response_id` — so the original response is never altered and re-scoring keeps history.
4. **Code** then evaluates deterministic threshold rules: **Rule 1** `sentiment < −0.3`, **Rule 2** `position = NOT_RECOMMENDED`, **Rule 3** a competitor sits materially above our therapy in the same response, and **Rule 4** `citation_status = WRONG_INDICATION` (the highest-severity rule).
5. An **OR gate (any rule true?)** combines them: if **no** rule fires → **No alert** (`alert_triggered = false`).
6. If **yes** → **Create alert + flag** (`alert_triggered = true`), recording which rule fired — the model produces the score, but only code makes the alert decision.

### 7. Data model (ERD)

Answers "what records exist and how are they linked — questions, runs, responses, scores, alerts, and the audit trail?"

```mermaid
erDiagram
  QUESTION ||--o{ RESPONSE : "asked in"
  LLM_TARGET ||--o{ RESPONSE : "answered by"
  RUN ||--o{ RESPONSE : "batches"
  RUN ||--o{ AUDIT_LOG : "logs"
  RESPONSE ||--o{ SCORING_RECORD : "scored, versioned"
  SCORING_RECORD ||--o{ ALERT : "raises"
  QUESTION {
    string question_id PK
    string question_text
    enum persona
    string therapeutic_area
    string brand_focus
    enum domain
    boolean active
    enum approval_status
    string approver_name
    int version
    timestamp created_at
    timestamp updated_at
  }
  LLM_TARGET {
    string target_id PK
    string llm_name
    string model_version
    string endpoint
    float temperature
    int max_tokens
    int rpm_limit
    int tpm_limit
    string personas
    boolean active
  }
  RUN {
    string run_id PK
    enum trigger_type
    timestamp started_at
    timestamp ended_at
    int questions_attempted
    int responses_captured
    int failure_count
    int total_tokens
    float est_cost
  }
  RESPONSE {
    uuid response_id PK
    string run_id FK
    string question_id FK
    string target_id FK
    timestamp timestamp_utc
    string llm_name
    string llm_model_version
    enum persona
    string therapeutic_area
    string brand_focus
    enum domain
    text response_text
    int response_tokens
    enum finish_reason
    enum status
    boolean alert_triggered
    timestamp created_at
  }
  SCORING_RECORD {
    uuid score_id PK
    uuid response_id FK
    float sentiment_score
    enum competitive_position
    json brand_mentions
    json key_claims
    text scoring_rationale
    string scorer_model
    int version
    boolean is_human_override
    timestamp created_at
  }
  ALERT {
    uuid alert_id PK
    uuid score_id FK
    uuid response_id FK
    enum rule_fired
    string reason
    timestamp created_at
  }
  AUDIT_LOG {
    uuid audit_id PK
    string run_id FK
    enum event_type
    string target
    timestamp ts
    int http_status
    string detail
  }
```

> An interactive version is also available: [`docs/diagrams/evidence_monitor_detailed_erd.html`](docs/diagrams/evidence_monitor_detailed_erd.html).

1. A **QUESTION** (with its persona, therapeutic area, brand focus, domain, approval status, and version) is *asked in* many **RESPONSE** records — one question, many answers.
2. An **LLM_TARGET** (its model version, parameters, and rate limits) *answers* many **RESPONSE** records — one target, many answers.
3. A **RUN** (with its trigger, timings, counts, tokens, and cost) *batches* many **RESPONSE** records and also *logs* many **AUDIT_LOG** entries.
4. Each **RESPONSE** is immutable and *scored* into many **SCORING_RECORD** versions — re-scoring adds a version, never overwrites.
5. Each **SCORING_RECORD** can *raise* many **ALERT** records, each noting the rule that fired.
6. Reading the "crow's-foot" ends: the single bar (`||`) is the *one* side and the branching foot (`o{`) is the *many* side, so the chain runs Question/Target/Run → Response → Scoring_Record → Alert, with Audit_Log hanging off the Run.

### 8. Local execution view

Answers "when this runs on one laptop, what processes, files, and folders are actually involved?"

![Local execution view](docs/diagrams/evidence_monitor_local_execution_view.svg)

1. Everything happens inside one **Local machine** — no cloud services in the POC.
2. **cron / APScheduler** (daily 02:00) launches the **Python process** (`evidence_monitor run`).
3. At startup the process reads **config + secrets** (`targets.yaml`, `.env`).
4. The process calls out over **HTTPS** to the **External LLM APIs** (OpenAI GPT-4o, Google Gemini, Anthropic Claude, and the conditional Open Evidence).
5. It writes its records to local storage: a **SQLite db** (all records) and an append-only **`audit.jsonl`**.
6. It also writes operational output: **`logs/`** (JSON events) and **`out/`** (the HTML dashboard and CSV exports) — everything the run produces stays on the local disk.

## How a run works

1. **Select** — load every question that is both `APPROVED` and active from the Question Repository.
2. **Dispatch** — for each question, submit it once to every configured target (Open Evidence only
   for Provider questions, if enabled). Transient failures retry with exponential backoff
   (3 attempts: 2s/4s/8s); after the budget the record is marked `FAILED` and the run continues.
3. **Persist** — store each answer as an immutable Response with full text, metadata, and status.
4. **Score** — Claude scores each response into a structured, versioned Scoring Record.
5. **Evaluate** — deterministic rules decide which responses raise an Alert.
6. **Summarize** — render the dashboard, write CSV/JSON exports, and produce a run summary.

Every step is checkpointed, so an interrupted run **resumes from the last completed question**
without re-submitting. Every external call is written to an **append-only audit log**.

## How scoring & alerts work

For each response, Claude returns a structured object (validated against a JSON schema):

- `sentiment_score` — `−1.0 … +1.0` toward the AbbVie therapy.
- `competitive_position` — `FIRST_LINE_RECOMMENDED | AMONG_OPTIONS | SECOND_LINE | NOT_RECOMMENDED | NOT_MENTIONED`.
- `citation_status` — `CITED | PARTIAL | ABSENT | WRONG_INDICATION`, where **WRONG_INDICATION**
  means the model returned content for the **wrong disease/indication** (a person routed to
  wrong-disease information).
- `brand_mentions` — the brands detected in the response.
- `key_claims` — up to five key claims the model made.
- `scoring_rationale` — a short explanation of the score.

**Code** (not the model) then applies **four deterministic alert rules**:

1. `sentiment_score` below the negative threshold (default **−0.3**, configurable).
2. `competitive_position` is `NOT_RECOMMENDED`.
3. A competitor brand has sentiment **≥0.3 higher** than the AbbVie therapy in the same response.
4. `citation_status` is `WRONG_INDICATION` → **highest-severity** alert.

## Tech stack

- **Python 3.11+**, managed with **uv**. **ruff** (format/lint), **pytest** (tests), **Pydantic** (schemas).
- **FastAPI** for the local Reports + Approvals app.
- **LangGraph** for the explicit, code-defined orchestration graph (no autonomous agent loops).
- **Anthropic API (Claude)** as orchestrator + scorer; **OpenAI** and **Google GenAI** SDKs for the
  monitored targets.
- **SQLite / DuckDB** behind a `data_access` interface. **APScheduler** (cron-compatible) for scheduling.
- Local-first: **no AWS services in the POC**.

## Repository guide

```text
.
├── README.md                     # You are here
├── CLAUDE.md                     # Golden rules + stack for Claude Code (agent context)
├── data/
│   └── question_bank.csv         # The 162-question bank (the ONLY place brand/competitor names live)
├── docs/
│   ├── SRS.pdf                   # Software Requirements Specification (source of scope)
│   ├── technical-architecture.md # Architecture, invariants, data model, ADR index, prod swap
│   ├── project-status.md         # LIVING status: phases, decisions, open items, how to resume
│   ├── adr/                      # Architecture Decision Records (0001–0007)
│   └── diagrams/                 # System, pipeline, orchestrator, ERD, sequence, etc.
├── specs/001-evidence-monitoring-poc/
│   ├── spec.md  plan.md  research.md  data-model.md  tasks.md  quickstart.md
│   ├── contracts/                # REST API, CLI, LLM adapter, scoring schema, data-access
│   └── checklists/requirements.md
├── src/evidence_monitor/         # Package code (built per tasks.md)
│   ├── config/ data_access/ llm/ question_repo/ response_repo/
│   ├── scoring/ alerts/ orchestrator/ dashboard/ observability/
│   ├── scheduler.py  cli.py  api.py
└── .specify/memory/constitution.md
```

## Claude Code setup

This repo is wired for [Claude Code](https://claude.com/claude-code):

- **Subagents** (`.claude/agents/`): `constitution-guardian` (checks staged changes against the 11
  principles), `test-runner`, `content-agnostic-auditor` (no hard-coded brands/secrets/PII),
  `data-explorer` (read-only DB/repo inspection).
- **Skills** (`.claude/skills/`): `/verify-phase`, `/add-llm-target`, `/import-question-bank`,
  `/capture-rate-eval`, `/scoring-schema-check` (plus the bundled `/speckit-*` workflow).
- **Hooks/permissions** (`.claude/settings.json`): a PostToolUse hook auto-runs `ruff format` +
  `ruff check --fix` on edited Python; read of `.env` is denied; `git push` and installs prompt.

## Spec-driven workflow

Built with **GitHub Spec Kit**. The chain — each step is a reviewed artifact:

```text
/speckit.constitution → /speckit.specify → /speckit.clarify → /speckit.plan
   → /speckit.tasks → /speckit.analyze → /speckit.checklist → /speckit.implement
```

Start from the constitution and spec; everything downstream traces back to them.

## How to run

> The POC is built; the commands below are the actual CLI (see
> [`specs/.../contracts/cli.md`](specs/001-evidence-monitoring-poc/contracts/cli.md) and
> [`quickstart.md`](specs/001-evidence-monitoring-poc/quickstart.md)).

**Offline / mock (no API keys, no network):**
```bash
uv sync
uv run evidence-monitor health-check --mock
uv run evidence-monitor import-questions --file data/question_bank.csv   # seed as PENDING
uv run evidence-monitor run --mock          # full capture → score → alert, all mocked
uv run pytest -q                            # unit + component + e2e (all offline)
```

The full mock pipeline is exercised end-to-end by `tests/e2e/` — a run over the whole seed bank
asserts **≥95% successful capture** (and that a flaky target never sinks the run) and that the
self-contained dashboard plus CSV/JSON exports are produced.

> `uv sync` installs the runtime deps **and** the dev tooling (pytest, ruff): they live in the
> default `dev` dependency group, so `uv run pytest` / `uv run ruff` work with no `--extra` flag.

**Live:** put `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY` (and optional
`OPEN_EVIDENCE_API_KEY`) in `.env`, approve questions in the Approvals UI, then:
```bash
uv run uvicorn evidence_monitor.api:app     # Reports + Approvals UI
uv run evidence-monitor run                 # a live run over APPROVED questions
```

A live `run` (or `subset`) runs a **startup credential preflight** first: if any required key is
missing it exits non-zero with a clear, non-secret error and submits nothing (FR-032). The same
presence gate backs `GET /health`. Resolved keys are registered for redaction, and all logs pass
through the secret-redacting formatter, so a credential can never reach a log sink. Keys live in
`.env`; the run bridges them into the environment so the provider SDKs authenticate.

### CLI commands

`uv run evidence-monitor <command>` (add `--mock` to any run for fully-offline, no-key execution):

| Command | What it does |
|---------|--------------|
| `import-questions --file <csv/xlsx>` | Import a curated question bank as **PENDING** (idempotent upsert by id). |
| `run [--target <id>] [--limit <n>]` | Full run over **APPROVED** questions: capture → score → alert. Live runs preflight credentials first. `--target` restricts to one configured target; `--limit` caps how many questions are dispatched. |
| `subset --persona/--therapeutic-area/--domain [--target <id>] [--limit <n>]` | Same as `run` over a filtered subset of approved questions. |
| `dry-run` | Validate config + target connectivity; write nothing. |
| `health-check` | **Real** minimal round-trip per **active** target (PASS only on a genuine 200; inactive targets are SKIPped, never probed). |
| `approve <id> --approver <name>` | Medical Affairs approval gate (`PENDING → APPROVED`); records the approver + an audit entry. |
| `reject <id> --approver <name> --reason <text>` | Reject a question (excluded from all runs); audited. |
| `approve-all-test-numbered` | **TEST only** (not MA sign-off): approve every active question with a numbered `approver-N` / `test-N`, idempotently. |
| `reset-to-pending` | Reset **all** questions to PENDING and clear approver/note — run before a real demo. |

The `approve`/`reject`/`approve-all-test-numbered`/`reset-to-pending` commands all go through the
question-repository approval seam and append to the append-only audit log — never raw SQL.

### Verify one provider at a time (smoke test)

When bringing up live credentials, verify each provider with a **real** call before a full run —
not the optimistic preflight:

```bash
uv run evidence-monitor health-check                              # real round-trip per active target
uv run evidence-monitor run --target anthropic-claude-target --limit 1   # one question, one target, end-to-end
```

With `--target`/`--limit` set, the run prints a per-response **capture + scoring confirmation**
(`[SUCCESS] … scored v1 sentiment=… position=… citation=…`), so you know capture *and* scoring
both worked for that target (a `[FAILED] … — <ErrorClass>` line shows the non-secret cause and
`not scored`). **Order matters:** Claude is the scorer for *every* target, so fix
`ANTHROPIC_API_KEY` first — once it works, the `openai-gpt4o` / `google-gemini` smoke tests both
capture and score.

### Local console (Reports + Approvals)

```bash
uv run uvicorn evidence_monitor.api:app     # serves http://127.0.0.1:8000 (local-only, no auth)
```

- **Reports tab** (`/?tab=reports`) — read-only sentiment / competitive-positioning / alerts / volume.
  Scope the view with the **Run** dropdown (or the date range) — e.g. pick today's clean run so a
  demo shows only good data while older debugging runs stay retained and auditable (nothing is
  deleted). Direct link: `/?tab=reports&run_id=<run_id>`.
- **Approvals tab** (`/?tab=approvals`) — the PENDING queue with approve/reject controls, plus a
  read-only **“Approved questions (N)”** view of every APPROVED + active question (id, persona,
  therapeutic area, brand focus, domain, status, approver, note, version, updated, full text),
  filterable by persona / therapeutic area / domain and a free-text search, sorted by `question_id`.

## Roadmap

- **Now:** POC build complete (per `tasks.md`) — capture & store → scoring → approval gate →
  alerts → dashboard, with an offline e2e suite asserting ≥95% capture. Next is the POC readout /
  acceptance validation.
- **Acceptance:** a 7-day unattended run with zero interventions, ≥95% capture, and a dashboard
  stakeholders confirm is actionable.
- **Production (future):** SQLite → Aurora/DynamoDB, Anthropic API → Bedrock, local scheduler →
  EventBridge, behind the same seams.
- **Vision (future, not POC):** GEO analysis, multi-agent architecture, literature-mining,
  pharmacovigilance signal detection.

## Data & compliance note

Questions are **generic and contain no PII/PHI**. Drug, competitor, and indication names exist
**only** in `data/question_bank.csv` and configuration — never in application code. Responses are
stored only in **local, controlled storage** and are never forwarded to third parties. The system
complies with each LLM provider's terms of service, every external call is **audit-logged**, and
**no question is submitted until a human has approved it**. Secrets are never logged.
