# ADR-0004: Immutable responses + versioned scoring records

**Status:** Accepted (2026-06-13)

## Context

For compliance and reproducibility, we must be able to prove exactly what each LLM said and when,
and to re-score responses (e.g., when the scoring prompt improves) without losing history or
corrupting the original answer.

## Decision

- A **Response** record is **immutable** once written — full text stored unedited; the repository
  raises on any update attempt.
- Derived data is a **separate, versioned `Scoring_Record`** linked by `response_id`. Re-scoring
  creates a new version; prior versions and the original response are never altered.
- Every external call is written to an **append-only audit log**.
- Deletes are **soft** (mark inactive with reason + timestamp); responses are retained ≥24 months
  and never physically purged in the POC.

## Options considered

- **Immutable response + versioned score (chosen)** — clean audit trail, safe re-scoring.
- **Mutable response with score columns** — simplest, but destroys history and violates
  Constitution II.
- **Overwrite scores in place** — loses the ability to compare scoring approaches over time.

## Consequences

- Storage grows with each re-score and never shrinks during the POC (acceptable; retention is a
  feature here).
- The `data_access` seam enforces write-once and versioning so business logic can't bypass it.

## Open follow-up

- Decide a production archival/cost strategy for the append-only data when moving to Aurora/DynamoDB.
