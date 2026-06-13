# Implementation Plan: Evidence Monitoring Agent — POC

**Branch**: `001-evidence-monitoring-poc` | **Date**: 2026-06-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-evidence-monitoring-poc/spec.md`

## Summary

Build a local-first POC that, on a daily schedule, submits every APPROVED question from a
versioned Question Repository to several public LLM targets, captures each response as an
immutable queryable record, scores each response with Claude (sentiment, competitive position,
citation status, brands, key claims, rationale) as a separate versioned record, raises
deterministic threshold alerts, and renders a self-contained HTML dashboard plus CSV/JSON
exports and a run summary — with an append-only audit log throughout.

Technical approach: an explicit, code-defined **LangGraph** orchestration graph (no autonomous
loops) drives the per-run flow; **Claude (Anthropic API)** is both orchestrator and scorer with
the model id sourced from config; monitored targets (OpenAI GPT-4o, Google Gemini, Claude as an
end-user, conditional Open Evidence) sit behind a uniform **adapter** seam with retry/backoff,
rate limiting, and a deterministic offline mock mode; all persistence sits behind a
**data-access** interface implemented on **SQLite/DuckDB**. Both seams (`llm`, `data_access`)
map cleanly to AWS in production (Bedrock, Aurora/DynamoDB) by config/implementation swap only.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI + Uvicorn (read-only Reports API, read-write local Approvals,
health check); LangGraph (explicit orchestration graph); `anthropic` SDK (orchestrator + scorer);
`openai` and `google-genai` SDKs (monitored targets); Pydantic v2 (schemas/validation); APScheduler
(scheduling; cron-compatible); Jinja2 (self-contained HTML render); httpx; ruff; pytest + pytest-cov.

**Storage**: SQLite (primary local store) with optional DuckDB for analytic reads, both behind a
`DataAccess`/`Repository` protocol in `data_access/`. Maps to Aurora (relational) + DynamoDB
(append-heavy audit) in production.

**Testing**: pytest at unit / component / e2e levels; ≥70% coverage on core modules; every LLM
adapter exercised in deterministic OFFLINE/MOCK mode; ruff for lint + format.

**Target Platform**: Local-first developer/operator machine (macOS/Linux). **No AWS services used
in the POC.**

**Project Type**: Single Python package (`src/evidence_monitor/`) exposing a CLI, a FastAPI app,
and a scheduled worker over shared core modules.

**Performance Goals**: A full daily run of ~100 questions × 3 targets (~300 calls) completes
within 4 hours at rate-limited cadence; scoring pass completes within 30 minutes of capture;
optional parallel dispatch across targets. ≥95% successful capture across targets.

**Constraints**: Local-first / offline-capable tests; deterministic alert rules; model ids,
parameters, rate limits, weights, cron, and token budget all externalized to config; secrets
never logged (redaction); responses immutable; runs resumable; startup credential preflight.

**Scale/Scope**: ≥100 active questions at launch, designed to scale to 1,000+ without
architectural change; 3–4 targets; daily + ad-hoc runs; 24-month retention via soft-delete.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design (below).*

Evaluated against Constitution v1.0.1 (all 11 principles). **Initial gate: PASS.**

| # | Principle | How the design satisfies it | Status |
|---|-----------|------------------------------|--------|
| I | Human approves, system suggests | `question_repo/approval.py` enforces PENDING→APPROVED→REJECTED; orchestrator queries only APPROVED; system performs no action beyond query/record/surface. | PASS |
| II | Immutable & auditable | `response_repo/repository.py` immutable writes; scoring stored as separate versioned record linked by `response_id`; `data_access/audit.py` append-only audit writer. | PASS |
| III | No PII/PHI | Questions generic; no PII fields in any schema; `observability/logging.py` redaction; tests assert no PII persisted. | PASS |
| IV | Content-agnostic code | Brand/competitor/indication strings live only in `question_repo` data and `config/targets.yaml`; code references them via data, never literals. Enforced by `content-agnostic-auditor`. | PASS |
| V | Config-driven targets | `config/settings.py` (env) + `config/targets.yaml`; adapters behind `llm/adapters/base.py`; model ids never hard-coded; add/remove target = config + adapter only. | PASS |
| VI | ToS & data residency | Responses stored only in local SQLite; no third-party forwarding; ToS acknowledgment recorded per target in config. | PASS |
| VII | Explain the score | `scoring/scorer.py` structured output always includes `brand_mentions`, ≤5 `key_claims`, `scoring_rationale`; schema-validated. | PASS |
| VIII | LLM scores, code decides | `alerts/rules.py` holds the 4 deterministic threshold rules; the scorer never decides alerts. | PASS |
| IX | Resilient & resumable | `llm/adapters/base.py` retry + exponential backoff + rate limiting; `orchestrator/run_manager.py` checkpoints after each persist and resumes from last completed question; FAILED marking; ≥95% target. | PASS |
| X | Built to grow into production | `data_access` and `llm` seams isolate all externals; AWS mapping documented below as a config/impl swap, not built now. | PASS |
| XI | Quality is testable | pytest unit/component/e2e; ≥70% core coverage; capture-rate and scoring-schema asserted by automated tests; ruff in CI gate. | PASS |

## Project Structure

### Documentation (this feature)

```text
specs/001-evidence-monitoring-poc/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (API, CLI, adapter, scoring, data-access)
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify + /speckit-clarify)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/evidence_monitor/
├── config/
│   ├── settings.py          # env-sourced: model ids, paths, alert weights/thresholds, cron, token budget
│   └── targets.yaml         # LLM targets: model versions, params, rate limits, personas, ToS ack
├── data_access/
│   ├── interface.py         # DataAccess + Repository protocols (the production seam)
│   ├── sqlite_store.py      # SQLite implementation (DuckDB analytic reads optional)
│   ├── queries.py           # filtered/paginated reads across query dimensions
│   └── audit.py             # append-only audit writer
├── llm/
│   ├── client.py            # Claude orchestrator + scorer (model id from config)
│   └── adapters/
│       ├── base.py          # adapter protocol: retry/backoff + rate limiting + OFFLINE/MOCK mode
│       ├── openai_gpt4o.py
│       ├── gemini.py        # safety-block handling → BLOCKED status
│       ├── claude_target.py # Claude queried as an end-user (distinct from orchestrator role)
│       └── open_evidence.py # conditional; Provider-persona only; deferred if no API access
├── question_repo/
│   ├── repository.py        # CRUD + versioning, no hard delete
│   ├── approval.py          # PENDING / APPROVED / REJECTED gate
│   └── importer.py          # CSV/Excel import (Medical Affairs curation)
├── response_repo/
│   ├── repository.py        # immutable writes
│   └── schema.py            # Pydantic response record
├── scoring/
│   ├── scorer.py            # structured JSON output (sentiment, position, citation, brands, claims, rationale)
│   └── prompts.py           # MA-reviewed scoring prompt
├── alerts/
│   └── rules.py             # 4 deterministic threshold rules incl. wrong-indication (highest severity)
├── orchestrator/
│   ├── state.py             # RunState
│   ├── nodes.py             # graph nodes (load → dispatch → persist → score → evaluate)
│   ├── graph.py             # LangGraph wiring (explicit, no autonomous loops)
│   └── run_manager.py       # run_id, resume from last completed question, checkpoint per persist
├── dashboard/
│   ├── render.py            # self-contained HTML (4 sections) + CSV/JSON export
│   └── template.html
├── observability/
│   ├── logging.py           # structured JSON logs + secret redaction
│   └── cost.py              # token + $ accounting
├── scheduler.py             # cron / APScheduler entry
├── cli.py                   # run / dry-run / subset / health-check
└── api.py                   # FastAPI: read-only Reports + read-write Approvals (local-only) + health

tests/
├── unit/                    # repositories, rules, scoring schema, adapters (mock), redaction, cost
├── component/               # question_repo + approval gate; orchestrator nodes; data_access queries
└── e2e/                     # full run in mock mode over seed → capture-rate + dashboard + resume
```

**Structure Decision**: Single Python package with three entry points (CLI, FastAPI app,
scheduler) over shared core modules. Module boundaries mirror the constitution's seams: `llm/`
(provider isolation, Principle V/X) and `data_access/` (storage isolation, Principle X). The
orchestration lives in `orchestrator/` as an explicit LangGraph graph (Principle VIII — code
decides). This is the DEFAULT single-project structure expanded with the spec-given layout.

## Production AWS Mapping (future swap — NOT built in the POC)

Each local component has a documented production target reachable by changing config/implementation
behind the `llm` and `data_access` seams — never by rewriting core logic (Principle X).

| Local (POC) | Production (AWS) | Seam / swap point |
|-------------|------------------|-------------------|
| APScheduler / cron (`scheduler.py`) | **Amazon EventBridge Scheduler** | scheduler entry config |
| Orchestration process (LangGraph in `orchestrator/`) | **AWS Fargate (ECS)** tasks; **Step Functions** for run-level orchestration/resume | run_manager + deployment |
| Claude orchestrator + scorer (`llm/client.py`, Anthropic API) | **Amazon Bedrock** (Claude) | `llm/client.py` + config model id |
| Monitored target adapters (`llm/adapters/*`) | Same provider SDKs or Bedrock-hosted equivalents | `llm/adapters/base.py` |
| SQLite/DuckDB (`data_access/sqlite_store.py`) | **Aurora** (relational: questions, runs, responses, scores, alerts) + **DynamoDB** (append-heavy audit log) | `data_access/interface.py` |
| Local HTML dashboard + CSV/JSON files (`dashboard/`) | **Amazon S3** (static hosting + export artifacts) | `dashboard/render.py` output sink |
| Structured JSON logs + cost (`observability/`) | **Amazon CloudWatch** (Logs + Metrics) | `observability/logging.py` sink |
| Env / `.env` secrets (`config/settings.py`) | **AWS Secrets Manager** | `config/settings.py` loader |
| FastAPI app (`api.py`) | **ALB + Fargate** | deployment only |

## Startup Credential Preflight

Per FR-007/IN-501/IN-502 and Principle VI, both `cli.py` and `api.py` run a preflight in
`config/settings.py` before any LLM query: validate that all **required** credentials are present
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`; `OPEN_EVIDENCE_API_KEY` only if the
conditional target is enabled) and **reachable** (lightweight connectivity/health ping per
configured target). If any required credential is missing or unreachable, the process exits with a
clear, non-secret error message and a non-zero status **before** submitting any question. The
`health-check` CLI subcommand and the API `/health` endpoint expose the same preflight on demand.

## Complexity Tracking

> No constitution violations. The table records deliberate complexity that the constitution
> **requires** (clean seams, explicit orchestration), with the simpler alternative and why it was
> rejected — included per the planning request.

| Deliberate choice | Why needed | Simpler alternative rejected because |
|-------------------|------------|--------------------------------------|
| `data_access` Repository protocol (not direct SQLite calls) | Principle X — must swap to Aurora/DynamoDB by config only | Direct DB calls in core would hard-couple storage and break the production swap |
| `llm/adapters` uniform protocol per provider | Principle V — add/remove target = config + adapter only; model ids from config | Per-provider branching in orchestration would put model logic in core and violate config-driven targets |
| LangGraph explicit graph (vs a plain function pipeline) | Principle VIII/IX — explicit nodes give checkpointable, resumable, code-decided flow | A monolithic loop is harder to checkpoint/resume and blurs the "code decides" boundary |
| Claude in two roles (orchestrator + scorer) | Spec/SRS requirement; both go through `llm/client.py` with config model ids | A single role can't both coordinate dispatch and produce the structured score the spec needs |
| Separate versioned `scoring` record (not fields on response) | Principle II — responses immutable; scores versioned/re-runnable | Mutating the response to add scores violates immutability and loses score history |
| Deterministic offline MOCK mode in every adapter | Principle XI — e2e + capture-rate tests must run without network | Live-only adapters make tests flaky, slow, and non-deterministic |

## Phase 0 — Research

See [research.md](./research.md). All Technical Context items are specified (no NEEDS
CLARIFICATION); research captures the key design decisions, rationale, and rejected alternatives.

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md) — entities, fields, relationships, state transitions, validation.
- [contracts/](./contracts/) — REST API, CLI, LLM adapter protocol, scoring output schema, data-access protocol.
- [quickstart.md](./quickstart.md) — runnable validation scenarios (mock-mode e2e, capture-rate, resume, dashboard).
- Agent context: `CLAUDE.md` SPECKIT block updated to reference this plan.

### Post-Design Constitution Re-Check

Re-evaluated after Phase 1 artifacts: **PASS** — the data model keeps responses immutable with a
separate versioned `ScoringRecord`; the data-access and adapter contracts preserve both seams;
the scoring contract guarantees explainability fields; the CLI/API contract keeps the system
advisory (read-only reports + approvals, no outbound action). No new violations introduced.
```
