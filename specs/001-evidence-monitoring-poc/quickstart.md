# Quickstart — Validate the Evidence Monitoring Agent POC

Runnable validation scenarios proving the feature works end-to-end. Detailed shapes live in
[data-model.md](./data-model.md) and [contracts/](./contracts/); implementation steps live in
`tasks.md` (created by `/speckit-tasks`). This guide is for **running and validating**, not coding.

## Prerequisites
- Python 3.11+ and `uv`.
- Install deps: `uv sync` — installs runtime deps **and** the default `dev` dependency group
  (pytest, ruff), so `uv run pytest` / `uv run ruff` need no `--extra` flag.
- For live runs only: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY` in `.env`
  (`OPEN_EVIDENCE_API_KEY` only if that conditional target is enabled).
- All validation below runs **offline** via `--mock` — no keys or network needed.

## Setup
```bash
uv sync
uv run evidence-monitor health-check --mock      # preflight passes in mock mode
uv run evidence-monitor import-questions --file data/question_bank.csv   # seed as PENDING
```

## Scenario 1 — Capture & store (US1, P1)
```bash
# Approve a seed set, then run fully offline:
uv run evidence-monitor run --mock
```
**Expect**: one immutable Response per (APPROVED question × target); statuses in
SUCCESS/FAILED/TRUNCATED/BLOCKED; an append-only audit entry per query/response; run summary
printed (attempted, captured-by-status, tokens). Re-running `--resume <run_id>` after an
interrupted run resumes from the last completed question (no re-submission).

## Scenario 2 — Scoring (US2, P2)
```bash
uv run evidence-monitor run --mock          # scoring pass runs after capture
```
**Expect**: each Response has a versioned ScoringRecord with `sentiment_score` ∈ [−1,1],
`competitive_position`, `citation_status`, `brand_mentions`, ≤5 `key_claims`, `scoring_rationale`,
validated against [scoring-output.schema.json](./contracts/scoring-output.schema.json). The
Response row is unchanged (immutable).

## Scenario 3 — Approval gate (US3, P2)
```bash
uv run uvicorn evidence_monitor.api:app      # open /approvals
```
**Expect**: PENDING questions are not submitted; approving sets APPROVED + approver; rejecting
excludes from runs; editing creates a new version with history retained.

## Scenario 4 — Alerts (US4, P2)
**Expect** (asserted by tests): an alert when `sentiment_score` < −0.3, `competitive_position` =
NOT_RECOMMENDED, a competitor brand scores ≥0.3 higher than our therapy in the same response, or
`citation_status` = WRONG_INDICATION (**highest severity**); no alert otherwise; identical inputs →
identical alert outcomes.

## Scenario 5 — Dashboard, export & summary (US5, P3)
```bash
uv run evidence-monitor run --mock           # writes dashboard.html + exports
```
**Expect**: a self-contained `dashboard.html` (no install) with sentiment distribution by LLM and
therapy, competitive positioning by LLM, alert list, and volume over time; drill-down shows full
text + rationale; CSV and JSON exports produced; run summary available via
`GET /reports/runs/{run_id}/summary`.

## Success validation (maps to spec Success Criteria)
```bash
uv run pytest -q                                  # unit + component + e2e
uv run pytest -q --cov=src/evidence_monitor       # ≥70% on core modules
```
- **SC-001/003**: e2e mock run of ~100 questions × 3 targets completes unattended with ≥95% capture.
- **SC-005**: query each dimension (llm/persona/TA/brand/domain/date/sentiment/alert) returns records.
- **SC-006/007**: every score carries brands+claims+rationale; alert tests pass at the thresholds.
- Resume, immutability, and schema-drift are covered by dedicated tests (and `/scoring-schema-check`).
