# Phase 0 — Research: Evidence Monitoring Agent POC

All Technical Context fields were specified in the planning input, so there are **no open
NEEDS CLARIFICATION items**. This document records the load-bearing design decisions, their
rationale, and the alternatives considered.

## D1 — Orchestration: LangGraph, explicit graph

- **Decision**: Model the per-run flow as an explicit LangGraph state graph
  (load APPROVED questions → dispatch to targets → persist response → score → evaluate alerts →
  summarize), with `RunState` carrying progress.
- **Rationale**: Principle VIII (code decides) and IX (resumable) — explicit nodes give a
  checkpointable, inspectable flow with no autonomous agent loop. Maps cleanly to Step Functions.
- **Alternatives**: A plain Python pipeline (harder to checkpoint/resume cleanly); an autonomous
  agent loop (rejected outright — violates "no autonomous loops" and "code decides").

## D2 — Claude in two roles via one client

- **Decision**: `llm/client.py` wraps the Anthropic API and serves both the orchestrator role and
  the scorer role; the monitored Claude *target* is a separate adapter (`claude_target.py`) queried
  as an end-user with a non-orchestrator system prompt. Role is tagged (ORCHESTRATOR | TARGET) in logs.
- **Rationale**: SRS IN-301/IN-302; keeps model ids from config (Principle V) and separates the
  scoring path from the monitored path while reusing one SDK client.
- **Alternatives**: Two separate SDK wrappers (duplicative); using a monitored target's output as a
  score (rejected — the scorer must be controlled and structured).

## D3 — Provider adapter seam with offline mock

- **Decision**: A `base.py` adapter protocol provides retry + exponential backoff (2s/4s/8s),
  per-provider rate limiting (rpm/tpm from config), and a deterministic OFFLINE/MOCK mode returning
  canned responses. Each provider (`openai_gpt4o`, `gemini`, `claude_target`, `open_evidence`)
  implements it. Gemini maps safety blocks to a `BLOCKED` status distinct from `FAILED`.
- **Rationale**: Principles V, IX, XI — config-driven targets, resilience, and network-free tests.
- **Alternatives**: Direct SDK calls in orchestration (couples model logic into core; rejected).

## D4 — Storage behind a data-access seam (SQLite now, Aurora/DynamoDB later)

- **Decision**: A `DataAccess`/`Repository` protocol (`interface.py`) with a SQLite implementation;
  DuckDB optional for analytic reads; an append-only audit writer. No core module touches SQL directly.
- **Rationale**: Principle X (production swap by config/impl only) and II (immutability/audit live
  behind the repository so they cannot be bypassed).
- **Alternatives**: An ORM spanning core (heavier, leaks storage choices); direct sqlite3 in modules
  (breaks the seam). Both rejected.

## D5 — Scoring as a separate versioned record + structured output

- **Decision**: The scorer returns a schema-validated JSON object (sentiment_score,
  competitive_position, citation_status, brand_mentions, key_claims ≤5, scoring_rationale) stored as
  a new `ScoringRecord` version linked to `response_id`; re-scoring adds a version.
- **Rationale**: Principles II and VII — immutability, versioning, explainability.
- **Alternatives**: Free-text scores parsed heuristically (brittle); scores as response columns
  (violates immutability). Rejected.

## D6 — Deterministic alert rules in code

- **Decision**: `alerts/rules.py` implements four deterministic rules: (1) sentiment_score below the
  configured negative threshold (default −0.3); (2) competitive_position = NOT_RECOMMENDED;
  (3) a competitor brand with sentiment ≥0.3 higher than our therapy in the same response;
  (4) citation_status = WRONG_INDICATION → **highest severity**. Thresholds/weights from config.
- **Rationale**: Principle VIII; clarify session set the ≥0.3 competitor margin.
- **Alternatives**: LLM-decided alerts (rejected — non-deterministic, violates Principle VIII).

## D7 — Resumability via per-question checkpointing

- **Decision**: `run_manager.py` assigns a `run_id`, persists each response before advancing, and
  checkpoints completed `question_id`s so an interrupted run resumes from the last completed question
  without re-submitting. Single submission per question/target/run (clarify decision).
- **Rationale**: Principle IX; SRS FR-504/NF-005.
- **Alternatives**: Whole-run retry (re-submits, wastes budget; rejected).

## D8 — Self-contained dashboard render

- **Decision**: `dashboard/render.py` renders a single self-contained HTML file (Jinja2 template,
  inlined assets) with four sections (sentiment distribution, competitive positioning, alerts,
  volume-over-time), plus CSV/JSON export and a run summary. No server needed to view.
- **Rationale**: SRS FR-601/FR-603 (no install). S3 static hosting in production.
- **Alternatives**: A live web app/SPA (heavier than POC needs; rejected for the readout artifact).

## D9 — Configuration & secrets

- **Decision**: `config/settings.py` sources env (model ids, paths, weights, cron, token budget);
  `config/targets.yaml` holds targets, model versions, params, rate limits, personas, ToS ack.
  Startup preflight validates required credentials present + reachable, else exits with a clear error.
- **Rationale**: Principles V/VI; SRS IN-501/IN-502/NF-009.
- **Alternatives**: Hard-coded model ids/params (violates Principle V; rejected).

## D10 — Observability & cost

- **Decision**: `observability/logging.py` emits structured JSON logs with a redaction filter for
  secret-shaped strings; `cost.py` accumulates tokens and estimated $ per run/target.
- **Rationale**: SRS NF-007/NF-014; constitution "secrets never logged."
- **Alternatives**: Plain text logs (not queryable; risk of secret leakage). Rejected.
