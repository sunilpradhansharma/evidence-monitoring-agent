---
description: "Task list for Evidence Monitoring Agent — POC"
---

# Tasks: Evidence Monitoring Agent — POC

**Input**: Design documents from `specs/001-evidence-monitoring-poc/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — every component is paired with a test task (explicitly requested;
also required by Constitution Principle XI).

**Organization**: Grouped by phase — Setup → Foundational → one phase per user story (priority
order) → Polish. All paths are relative to the repository root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US5 maps to the spec's user stories
- Exact file paths are included in every task

---

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 Create the package + test tree per plan.md: `src/evidence_monitor/{config,data_access,llm/adapters,question_repo,response_repo,scoring,alerts,orchestrator,dashboard,observability}/__init__.py` and `tests/{unit,component,e2e}/__init__.py`
- [ ] T002 Initialize the uv project in `pyproject.toml` with runtime deps (fastapi, uvicorn, langgraph, anthropic, openai, google-genai, pydantic, apscheduler, jinja2, httpx) and dev deps (pytest, pytest-cov, ruff); define the `evidence-monitor` console script → `src/evidence_monitor/cli.py`
- [ ] T003 [P] Configure ruff + pytest in `pyproject.toml` (ruff rules/format; `[tool.pytest.ini_options]` test paths and `--cov=src/evidence_monitor`)
- [ ] T004 [P] Populate `.env.example` with required keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, optional `OPEN_EVIDENCE_API_KEY`) and config overrides (paths, cron, token budget)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The seams and shared primitives every component depends on. **⚠️ No user-story work
may begin until this phase is complete.** (Per the task request: data-access interface, SQLite
store, Pydantic schemas, audit log, and the no-PII seed generator come first.)

- [ ] T005 Create shared enums + entity Pydantic schemas (Question, LLMTarget, Run, ScoringRecord, Alert, AuditEvent) in `src/evidence_monitor/data_access/models.py` per data-model.md
- [ ] T006 [P] Unit test for enums + schema validation (ranges, `key_claims` ≤5, no-PII fields) in `tests/unit/test_models.py`
- [ ] T007 Create the immutable Response record schema in `src/evidence_monitor/response_repo/schema.py`
- [ ] T008 [P] Unit test for the Response schema in `tests/unit/test_response_schema.py`
- [ ] T009 Define `DataAccess` + Repository protocols (Question/Response/Scoring/Alert/Run/AuditWriter) in `src/evidence_monitor/data_access/interface.py` per contracts/data-access.md
- [ ] T010 [P] Unit test asserting protocol surface + query filter object in `tests/unit/test_interface_contracts.py`
- [ ] T011 Implement the SQLite store (schema creation/migrations + Question/Response/Run repos) in `src/evidence_monitor/data_access/sqlite_store.py`
- [ ] T012 [P] Component test for SQLite store round-trips + write-once Response in `tests/component/test_sqlite_store.py`
- [ ] T013 Implement the append-only audit writer (no update/delete) in `src/evidence_monitor/data_access/audit.py`
- [ ] T014 [P] Unit test asserting audit append-only behavior in `tests/unit/test_audit.py`
- [ ] T015 Implement env-sourced settings + startup credential preflight in `src/evidence_monitor/config/settings.py` and create `src/evidence_monitor/config/targets.yaml` (targets, model versions, params, rate limits, personas, ToS ack)
- [ ] T016 [P] Unit test for settings load + preflight exits clearly on missing/unreachable creds in `tests/unit/test_settings.py`
- [ ] T017 Implement structured JSON logging + secret redaction in `src/evidence_monitor/observability/logging.py`
- [ ] T018 [P] Unit test asserting secrets are redacted and never logged in `tests/unit/test_logging_redaction.py`
- [ ] T019 Implement the generic, **no-PII** seed question generator in `src/evidence_monitor/question_repo/seed.py` (produces persona-tagged generic questions for tests/demo)
- [ ] T020 [P] Unit test asserting seeded questions contain no PII/PHI and cover all personas in `tests/unit/test_seed_no_pii.py`

**Checkpoint**: Foundation ready — user stories can begin.

---

## Phase 3: User Story 1 — Automated capture & storage (Priority: P1) 🎯 MVP

**Goal**: A scheduled, unattended run submits every APPROVED question to every configured target,
stores each response as an immutable queryable record with status, retries/backoff on failure,
audits every call, and resumes from the last completed question.

**Independent Test**: Seed + approve questions, run `--mock`, confirm one immutable record per
(question × target) with SUCCESS/FAILED/TRUNCATED/BLOCKED, append-only audit entries, and that
`--resume` skips completed questions.

- [ ] T021 [US1] Implement the adapter protocol (retry + exponential backoff + rate limiting + OFFLINE/MOCK mode) in `src/evidence_monitor/llm/adapters/base.py` per contracts/llm-adapter.md
- [ ] T022 [P] [US1] Unit test for base adapter retry/backoff + deterministic mock in `tests/unit/test_adapter_base.py`
- [ ] T023 [P] [US1] Implement the OpenAI GPT-4o adapter in `src/evidence_monitor/llm/adapters/openai_gpt4o.py`
- [ ] T024 [P] [US1] Unit test (mock mode) for the OpenAI adapter in `tests/unit/test_openai_adapter.py`
- [ ] T025 [P] [US1] Implement the Gemini adapter with safety-block → BLOCKED mapping in `src/evidence_monitor/llm/adapters/gemini.py`
- [ ] T026 [P] [US1] Unit test (mock mode, BLOCKED path) for the Gemini adapter in `tests/unit/test_gemini_adapter.py`
- [ ] T027 [P] [US1] Implement the Claude-as-end-user target adapter in `src/evidence_monitor/llm/adapters/claude_target.py`
- [ ] T028 [P] [US1] Unit test (mock mode) for the Claude target adapter in `tests/unit/test_claude_target_adapter.py`
- [ ] T029 [P] [US1] Implement the conditional Open Evidence adapter (PROVIDER persona only, enabled by config) in `src/evidence_monitor/llm/adapters/open_evidence.py`
- [ ] T030 [P] [US1] Unit test for Open Evidence gating (skipped when disabled / non-Provider) in `tests/unit/test_open_evidence_adapter.py`
- [ ] T031 [US1] Implement the Claude orchestrator client (model id from config) in `src/evidence_monitor/llm/client.py`
- [ ] T032 [P] [US1] Unit test for the orchestrator client config sourcing in `tests/unit/test_llm_client.py`
- [ ] T033 [US1] Implement immutable Response writes in `src/evidence_monitor/response_repo/repository.py`
- [ ] T034 [P] [US1] Component test asserting Response immutability (update raises) in `tests/component/test_response_immutability.py`
- [ ] T035 [US1] Implement filtered/paginated reads across all query dimensions in `src/evidence_monitor/data_access/queries.py`
- [ ] T036 [P] [US1] Component test for query filters + pagination in `tests/component/test_queries.py`
- [ ] T037 [US1] Implement token + cost accounting in `src/evidence_monitor/observability/cost.py`
- [ ] T038 [P] [US1] Unit test for cost/token accounting in `tests/unit/test_cost.py`
- [ ] T039 [US1] Implement `RunState` in `src/evidence_monitor/orchestrator/state.py`
- [ ] T040 [US1] Implement load→dispatch→persist nodes in `src/evidence_monitor/orchestrator/nodes.py`
- [ ] T041 [P] [US1] Component test for capture nodes (per-target dispatch, status mapping) in `tests/component/test_orchestrator_nodes.py`
- [ ] T042 [US1] Wire the explicit LangGraph graph (no autonomous loops) in `src/evidence_monitor/orchestrator/graph.py`
- [ ] T043 [US1] Implement run lifecycle: run_id, checkpoint after each persist, resume from last completed question in `src/evidence_monitor/orchestrator/run_manager.py`
- [ ] T044 [P] [US1] Component test for resume-from-checkpoint (no re-submission) in `tests/component/test_run_resume.py`
- [ ] T045 [US1] Implement CLI `run` / `dry-run` / `subset` / `health-check` (with preflight) in `src/evidence_monitor/cli.py` per contracts/cli.md
- [ ] T046 [P] [US1] Component test for CLI commands (mock) in `tests/component/test_cli.py`
- [ ] T047 [US1] Implement the cron/APScheduler entry in `src/evidence_monitor/scheduler.py`
- [ ] T048 [P] [US1] Unit test for scheduler trigger wiring in `tests/unit/test_scheduler.py`

**Checkpoint**: A full capture-and-store run works unattended in mock mode (MVP).

---

## Phase 4: User Story 2 — Scoring (Priority: P2)

**Goal**: After capture, a scoring pass produces a schema-validated, versioned ScoringRecord per
response (sentiment, competitive position, citation status, brands, ≤5 claims, rationale) without
mutating the response.

**Independent Test**: Run scoring over stored responses; confirm each gets a versioned
ScoringRecord validating against `contracts/scoring-output.schema.json`; re-scoring adds a version
and leaves the response unchanged.

- [ ] T049 [US2] Author the MA-reviewed scoring prompt in `src/evidence_monitor/scoring/prompts.py`
- [ ] T050 [US2] Implement the scorer with structured JSON output (validated vs the scoring schema) in `src/evidence_monitor/scoring/scorer.py`
- [ ] T051 [P] [US2] Unit test asserting scorer output conforms to `contracts/scoring-output.schema.json` in `tests/unit/test_scorer_schema.py`
- [ ] T052 [US2] Implement `ScoringRepository` (add_version / latest_for / versions_for) in `src/evidence_monitor/data_access/sqlite_store.py`
- [ ] T053 [P] [US2] Component test for scoring versioning + response-immutability preserved in `tests/component/test_scoring_versioning.py`
- [ ] T054 [US2] Add the scoring node to `src/evidence_monitor/orchestrator/nodes.py` and wire it into `graph.py`
- [ ] T055 [P] [US2] Component test for the end-to-end scoring pass (mock) in `tests/component/test_scoring_pass.py`

**Checkpoint**: Stored responses are scored into versioned records.

---

## Phase 5: User Story 3 — Question curation & approval gate (Priority: P2)

**Goal**: Medical Affairs curates a versioned repository and controls eligibility via
PENDING→APPROVED→REJECTED; only APPROVED questions are submitted.

**Independent Test**: Create/edit/approve/reject questions; confirm runs submit only APPROVED, and
edits create new versions with history retained.

- [ ] T056 [US3] Implement question CRUD + versioning (no hard delete) in `src/evidence_monitor/question_repo/repository.py`
- [ ] T057 [P] [US3] Component test for question versioning + soft-delete in `tests/component/test_question_versioning.py`
- [ ] T058 [US3] Implement the approval state machine (PENDING/APPROVED/REJECTED, approver recorded) in `src/evidence_monitor/question_repo/approval.py`
- [ ] T059 [P] [US3] Component test asserting only APPROVED+active questions are run-eligible in `tests/component/test_approval_gate.py`
- [ ] T060 [US3] Implement the CSV/Excel importer (idempotent upsert by question_id, imports as PENDING) in `src/evidence_monitor/question_repo/importer.py`
- [ ] T061 [P] [US3] Component test for idempotent import (no duplicates) in `tests/component/test_importer.py`
- [ ] T062 [US3] Implement the read-write Approvals endpoints in `src/evidence_monitor/api.py` per contracts/rest-api.md
- [ ] T063 [P] [US3] Component test for the Approvals API (approve/reject/edit) in `tests/component/test_approvals_api.py`

**Checkpoint**: Curation + approval gate enforced end to end.

---

## Phase 6: User Story 4 — Threshold alerts (Priority: P2)

**Goal**: Deterministic, code-only threshold rules raise alerts on concerning responses, with
WRONG_INDICATION at highest severity. (Alert rules are intentionally a **separate code-only task
from the Claude scoring task** — Principle VIII.)

**Independent Test**: Feed scoring records across the boundaries; confirm an alert fires exactly
when a rule matches, WRONG_INDICATION is highest severity, and identical inputs → identical results.

- [ ] T064 [US4] Implement the 4 deterministic threshold rules (negative sentiment < −0.3; NOT_RECOMMENDED; competitor ≥0.3 higher; WRONG_INDICATION highest severity) — **code only, no LLM** — in `src/evidence_monitor/alerts/rules.py`
- [ ] T065 [P] [US4] Unit test for rule boundaries + determinism + severity ordering in `tests/unit/test_alert_rules.py`
- [ ] T066 [US4] Implement `AlertRepository` persistence + denormalized `alert_triggered` on the response view in `src/evidence_monitor/data_access/sqlite_store.py`
- [ ] T067 [P] [US4] Component test for alert persistence + severity ordering in `tests/component/test_alert_persistence.py`
- [ ] T068 [US4] Add the evaluate-alerts node to `src/evidence_monitor/orchestrator/nodes.py` and wire it into `graph.py`
- [ ] T069 [P] [US4] Component test for the evaluate-alerts node (mock) in `tests/component/test_evaluate_alerts.py`

**Checkpoint**: Alerts are raised deterministically from scores.

---

## Phase 7: User Story 5 — Dashboard, export & run summary (Priority: P3)

**Goal**: A self-contained HTML dashboard (4 sections) with drill-down, CSV/JSON export, read-only
Reports API, and a run summary — no install.

**Independent Test**: After a scored run, open `dashboard.html`, verify the 4 sections + drill-down,
export CSV/JSON, and fetch the run summary.

- [ ] T070 [US5] Create the dashboard Jinja2 template in `src/evidence_monitor/dashboard/template.html`
- [ ] T071 [US5] Implement self-contained HTML render (sentiment distribution, competitive positioning, alerts, volume-over-time) + CSV/JSON export in `src/evidence_monitor/dashboard/render.py`
- [ ] T072 [P] [US5] Component test for dashboard render + exports in `tests/component/test_dashboard_render.py`
- [ ] T073 [US5] Implement the read-only Reports endpoints (responses, drill-down, export, alerts) in `src/evidence_monitor/api.py` per contracts/rest-api.md
- [ ] T074 [P] [US5] Component test for the Reports API in `tests/component/test_reports_api.py`
- [ ] T075 [US5] Implement the run summary (run_id, timings, captured-by-status, alert count, tokens) via `src/evidence_monitor/orchestrator/run_manager.py` and `GET /reports/runs/{run_id}/summary`
- [ ] T076 [P] [US5] Component test for the run summary in `tests/component/test_run_summary.py`
- [ ] T077 [US5] Implement the `/health` endpoint (shared preflight) in `src/evidence_monitor/api.py`
- [ ] T078 [P] [US5] Component test for `/health` (ok + degraded) in `tests/component/test_health_endpoint.py`

**Checkpoint**: Findings are consumable by stakeholders without install.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T079 [P] End-to-end mock run over the seed (quickstart scenarios 1–5) in `tests/e2e/test_full_run_mock.py`
- [ ] T080 [P] E2E capture-rate test asserting ≥95% successful capture in `tests/e2e/test_capture_rate.py`
- [ ] T081 Enforce ≥70% coverage on core modules via `pyproject.toml` pytest-cov config and verify `uv run pytest --cov=src/evidence_monitor`
- [ ] T082 [P] Run the `content-agnostic-auditor` over `src/` to confirm no hard-coded brand/competitor/indication literals (Principle IV)
- [ ] T083 [P] Write `README.md` at the repo root: setup, env vars, adding a target, importing questions (NF-011)
- [ ] T084 Final `uv run ruff format .` + `uv run ruff check --fix .` clean pass
- [ ] T085 Execute `specs/001-evidence-monitoring-poc/quickstart.md` end to end and confirm all scenarios pass

---

## Dependencies & Execution Order

### Phase dependencies
- **Setup (P1)** → no deps.
- **Foundational (P2)** → depends on Setup; **blocks all user stories**.
- **US1 (P3)** → depends on Foundational only (MVP).
- **US2 (P4)** → Foundational; consumes US1's stored responses for a full pass (scorer is unit-testable alone).
- **US3 (P5)** → Foundational; independent (feeds the approval gate US1's run reads).
- **US4 (P6)** → Foundational + US2 (operates on ScoringRecords; rules are unit-testable alone).
- **US5 (P7)** → Foundational + US1 (+ US2/US4 data to populate all sections).
- **Polish (P8)** → after the desired stories.

### Within each story
Tests are written to fail first → models/schemas → repositories → services → orchestrator nodes →
endpoints/CLI. Different files marked **[P]** can run together.

### Parallel opportunities
- Setup: T003, T004 in parallel.
- Foundational: each test (T006/T008/T010/T012/T014/T016/T018/T020) is **[P]** with its sibling impl done; the 8 components are largely independent once `models.py` (T005) and `interface.py` (T009) exist.
- US1: all five adapters (T023/T025/T027/T029 + base T021) and their tests run in parallel; cost (T037), queries (T035), response repo (T033) are independent.
- Across stories: once Foundational is done, US1, US3 can proceed fully in parallel; US2 then US4 then US5 layer on.

---

## Parallel Example: User Story 1 adapters

```bash
# After T021 (base.py) lands, implement the four core adapters in parallel:
Task: "Implement OpenAI GPT-4o adapter in src/evidence_monitor/llm/adapters/openai_gpt4o.py"   # T023
Task: "Implement Gemini adapter in src/evidence_monitor/llm/adapters/gemini.py"                  # T025
Task: "Implement Claude target adapter in src/evidence_monitor/llm/adapters/claude_target.py"    # T027
Task: "Implement Open Evidence adapter in src/evidence_monitor/llm/adapters/open_evidence.py"     # T029
```

---

## Implementation Strategy

### MVP first (User Story 1 only)
1. Phase 1 Setup → 2. Phase 2 Foundational (critical) → 3. Phase 3 US1 → **STOP & validate** a
mock capture run with resume → demo. This alone is a usable artifact (stored, queryable responses).

### Incremental delivery
Foundational → US1 (MVP) → US2 (scores) → US3 (approval gate) → US4 (alerts) → US5 (dashboard),
validating each independently before the next.

### Parallel team strategy
After Foundational: Dev A → US1; Dev B → US3 (curation/approval); then US2 → US4 (depend on
scoring) and US5 (dashboard) as data becomes available.

---

## Notes
- **[P]** = different files, no incomplete-task dependency.
- Each component has a paired test (per request + Principle XI); write tests to fail first.
- Alert rules (T064) are deliberately code-only and separate from the Claude scorer (T050) —
  Principle VIII (LLM scores, code decides).
- Commit after each task or logical group; stop at any checkpoint to validate a story.
- Total: 85 tasks (T001–T085).
