# Contract — CLI (`evidence-monitor`)

`cli.py`. Invoked as `uv run evidence-monitor <command>`. Every command runs the credential
preflight first and exits non-zero with a clear message if a required credential is missing or
unreachable.

## `run`
Execute a full run: for each APPROVED+active question, submit to every configured target, persist
each response immutably, score, evaluate alerts, render dashboard, write run summary.
- **Options**: `--resume <run_id>` (resume from last completed question), `--targets a,b`
  (subset of configured targets), `--no-score` (capture only).
- **Exit**: `0` if run completes (even with some FAILED records within the ≥95% budget); non-zero
  if capture rate falls below the configured floor or a fatal error occurs.

## `dry-run`
Validate connectivity + config for all targets and resolve the APPROVED question set **without
writing** to the Response Repository (SRS FR-209).
- **Output**: per-target reachability, the count of questions that would be submitted, estimated
  token budget.

## `subset`
Run against a filtered slice (SRS FR-210) for targeted monitoring outside the daily cadence.
- **Options**: `--persona`, `--therapeutic-area`, `--domain`, `--brand`, `--limit`.

## `health-check`
Run the preflight and print target reachability + a status report (SRS NF-009). Exit `0` if all
required targets reachable, else non-zero.

## `import-questions`
Import the question bank from CSV/Excel into the Question Repository as PENDING (idempotent upsert
by `question_id`). Mirrors the `/import-question-bank` skill.
- **Options**: `--file <path>`, `--dry-run`.

## Global
- `--config <path>` overrides `config/` location; `--mock` forces adapter OFFLINE mode (tests/demo);
  `--log-level`. Model ids, params, rate limits, cron, weights, and token budget come from config,
  never CLI literals (Principle V).
