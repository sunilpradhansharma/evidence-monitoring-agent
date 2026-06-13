# ADR-0002: Local-first POC with a production swap behind seams

**Status:** Accepted (2026-06-13)

## Context

The POC must be cheap and fast to run, demonstrable on a single machine, and free of cloud setup —
yet it must also be a credible prototype of a production system on AWS, not a throwaway. The SRS
calls for SQLite + Anthropic API locally, with Aurora/DynamoDB + Bedrock in production.

## Decision

Build **local-first** (SQLite/DuckDB storage, Anthropic API, APScheduler/cron, local HTML
dashboard) and isolate every external dependency behind two clean seams:

- **`data_access`** — Repository protocols; SQLite now, Aurora/DynamoDB later.
- **`llm`** — adapter protocol + a Claude client; Anthropic API now, Bedrock later.

Moving to production is a **configuration/implementation swap behind these seams**, never a rewrite
of core logic (Constitution X). **No AWS services are used in the POC.**

## Options considered

- **Local-first behind seams (chosen)** — cheap, demonstrable, production-credible.
- **Build directly on AWS** — most production-faithful, but slow/expensive to iterate and overkill
  for a POC.
- **Local with no abstraction seams** — fastest to write, but would require a rewrite to productionize.

## Consequences

- The repository/adapter indirection adds a little ceremony now.
- Production mapping is documented (see `technical-architecture.md` §14) and testable via mock mode.
- The same tests run offline, keeping CI fast and deterministic.

## Open follow-up

- Confirm the production targets (Aurora vs DynamoDB split, Bedrock model availability) before any
  production work begins.
