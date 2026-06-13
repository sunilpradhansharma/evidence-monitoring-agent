# Evidence Monitoring Agent

LLM-based evidence-monitoring POC. Claude scores brand/competitor evidence from a question
bank; **code** makes the alerting decisions.

## Golden rules (non-negotiable)
- **Responses are immutable; scores are versioned.** Never mutate a stored response in place.
- **No PII** anywhere — code, fixtures, logs, comments.
- **No hard-coded drug / competitor / indication names in code.** They live ONLY in data
  (`data/question_bank.csv` and the question repo). Config defaults must stay content-agnostic.
- **Model ids and target settings come only from config** (`config/targets.yaml`).
- **Claude scores; code decides alerts.** No alert/decision taken straight from model output.
- **Secrets are never logged.** Read of `.env` is denied by project settings.

## Stack
- **Python 3.11+**, managed with **uv**. **ruff** for format + lint, **pytest** for tests,
  **Pydantic** for models/validation.
- **FastAPI** for the service layer.
- **LangGraph** for orchestration — explicit, code-defined flow; **no autonomous agent loops**.
- **Anthropic API (Claude)** is the orchestrator + scorer. **Amazon Bedrock** is the documented
  production swap (config/implementation only).
- **Monitored targets** via the **OpenAI** and **Google GenAI** SDKs, behind the `llm` seam.
- **SQLite / DuckDB** behind a **`data_access`** interface for the question repo and stored scores.
- Per-provider **LLM adapters** under `src/evidence_monitor/llm/adapters/` (see that folder's
  `CLAUDE.md` for adapter rules).
- **Local-first: no AWS services are used in the POC.**
- **Spec Kit** drives the spec → plan → tasks → implement workflow (`/speckit-*`).

## Commands
- Tests: `uv run pytest -q`
- Format / lint: `uv run ruff format .` · `uv run ruff check --fix .`
- App: `uv run evidence-monitor ...`
- Skills: `/verify-phase` · `/import-question-bank` · `/capture-rate-eval` ·
  `/add-llm-target <name>` · `/scoring-schema-check`
- A PostToolUse hook auto-runs ruff format + `--fix` on every edited `.py` file.

## Layout conventions
- `config/` — YAML config (targets, settings). `data/` — seed data. `tests/` — pytest suite.
- `src/evidence_monitor/` — package code. `.specify/` — Spec Kit artifacts.

## Detail lives in imports (loaded on demand, not duplicated here)
- Constitution / principles: @.specify/memory/constitution.md
- POC spec: @specs/001-evidence-monitoring-poc/spec.md

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
<!-- SPECKIT END -->
