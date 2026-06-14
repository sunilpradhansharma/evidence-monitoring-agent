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
| [0005](adr/0005-combined-local-ui.md) | Combined Reports + Approvals UI, local-only, approver-name, no RBAC |
| [0006](adr/0006-citation-status-wrong-indication.md) | `citation_status` with `WRONG_INDICATION` + highest-severity alert |
| [0007](adr/0007-offline-e2e-capture-rate-and-cli-preflight.md) | Offline e2e capture-rate gate + CLI credential preflight |

## 4. Module / package map

```text
src/evidence_monitor/
├── config/         settings.py (env: model ids, paths, thresholds, cron, token budget)
│                   targets.yaml (targets, model versions, params, rate limits, personas, ToS ack)
├── data_access/    interface.py (DataAccess + Repository protocols)  ← the storage seam
│                   sqlite_store.py, queries.py (filtered/paginated reads), audit.py (append-only)
├── llm/            client.py (Claude orchestrator + scorer; model id from config)  ← the LLM seam
│                   adapters/ base.py (retry/backoff, rate limit, mock), openai_gpt4o.py,
│                            gemini.py (safety→BLOCKED), claude_target.py, open_evidence.py
├── question_repo/  repository.py (CRUD + versioning), approval.py (gate), importer.py (CSV/Excel), seed.py
├── response_repo/  repository.py (immutable writes), schema.py (Response record)
├── scoring/        scorer.py (structured JSON), prompts.py (MA-reviewed prompt)
├── alerts/         rules.py (4 deterministic rules incl. wrong-indication)
├── orchestrator/   state.py, nodes.py, graph.py (LangGraph), run_manager.py (run_id, resume, checkpoint)
├── dashboard/      render.py (self-contained HTML + CSV/JSON), template.html
├── observability/  logging.py (structured JSON + secret redaction), cost.py (tokens + $)
├── scheduler.py    cron / APScheduler entry
├── cli.py          run / dry-run / subset / health-check
└── api.py          FastAPI: read-only Reports + read-write Approvals + /health
```

## 5. The `data_access` seam

All persistence goes through protocols in `data_access/interface.py`
([contract](../specs/001-evidence-monitoring-poc/contracts/data-access.md)) —
`QuestionRepository`, `ResponseRepository`, `ScoringRepository`, `AlertRepository`,
`RunRepository`, and the `AuditWriter`. Core modules depend only on these protocols, so the
SQLite implementation can be replaced by an Aurora/DynamoDB one without touching business logic.
The seam is where immutability, versioning, append-only audit, and soft-delete/retention are
**enforced**, not merely encouraged.

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
- **Offline/mock mode** — deterministic canned results with no network call, so e2e and
  capture-rate tests are fast and repeatable.
- **Config-sourced** — model ids/params/endpoints are never hard-coded. Adding a target is a new
  adapter + a `targets.yaml` entry, with no change to orchestration.

Claude plays two roles through `llm/client.py`: the **orchestrator** and the **scorer**. The
monitored Claude *target* is a separate adapter queried as an end-user; calls are tagged
`ORCHESTRATOR` vs `TARGET` in the audit log.

## 9. Scoring + the four alert rules

The scorer (`scoring/scorer.py`) returns a JSON object validated against
[`scoring-output.schema.json`](../specs/001-evidence-monitoring-poc/contracts/scoring-output.schema.json):
`sentiment_score (−1..+1)`, `competitive_position`, `citation_status`, `brand_mentions`,
`key_claims (≤5)`, `scoring_rationale`. The result is stored as a new `Scoring_Record` version.

`alerts/rules.py` then applies **deterministic** rules (see `scoring_and_alert_decision_flow.svg`):

1. `sentiment_score` < negative threshold (default **−0.3**).
2. `competitive_position` == `NOT_RECOMMENDED`.
3. competitor brand sentiment ≥ **0.3** higher than the AbbVie therapy in the same response.
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
- Entry points: `cli.py` (`run` / `import-questions` / `dry-run` / `subset` / `health-check` /
  `approve` / `reject`; a live `run`/`subset` runs the credential preflight first), `scheduler.py`
  (daily cron), `api.py` (Reports + Approvals + `/health`).

## 14. POC → production

The seams make production a configuration/implementation swap, not a rewrite (Constitution X):

| Concern | POC (local) | Production (AWS) | Swap point |
|---------|-------------|------------------|------------|
| Storage | SQLite / DuckDB | **Aurora** (relational) + **DynamoDB** (audit) | `data_access/interface.py` |
| Claude (orchestrator + scorer) | Anthropic API | **Amazon Bedrock** | `llm/client.py` + config |
| Scheduling | APScheduler / cron | **Amazon EventBridge Scheduler** | `scheduler.py` |
| Orchestration runtime | local process | **Fargate** + **Step Functions** | deployment + `run_manager` |
| Dashboard / exports | local HTML files | **Amazon S3** | `dashboard/render.py` |
| Logs / metrics | structured JSON files | **CloudWatch** | `observability/logging.py` |
| Secrets | env / `.env` | **AWS Secrets Manager** | `config/settings.py` |
