# ADR-0009: Version-aware question counts (latest version per `question_id`)

**Status:** Accepted (2026-06-14)

## Context

Questions are immutable and **versioned**: every edit, approval, or deactivation appends a new
row to the `questions` table (primary key `(question_id, version)`); history is never overwritten
(ADR-0004, FR-001). The Approvals UI and the Reports approval-gate metric show counts of questions
by status (pending / approved / rejected / total) and an approved-vs-pending figure.

A naive count over the raw `questions` table counts **every version**, so a question edited or
re-approved several times is counted multiple times — over-stating the totals and letting the same
question appear more than once in a list. The correct unit is **one question = its latest version**.

## Decision

Every question count and list is computed over the **latest version per `question_id`**, using the
version-aware read path the store already exposes (`QuestionRepository.list` →
`_latest_all`, which selects `MAX(version)` per `question_id`). On top of that, the dashboard layer
applies a defensive `render.latest_per_question(...)` at the row-rendering boundary so a list can
never leak version history even if an upstream query changes.

This applies uniformly to:

- the approval-gate counts in the Reports payload (`render.build_report` → `_approval_gate`),
- the Approvals status counts and the pending / approved / rejected lists (HTML and `/api/questions`),
- the capture-rate / per-run response metrics, which are scoped to the selected `run_id`.

The behavior is asserted by tests (`tests/component/test_ui_redesign.py`,
`tests/component/test_json_api.py`): a question edited to v2/v3 is counted once and appears once.

## Options considered

- **Latest-version-per-question everywhere (chosen)** — matches the real-world unit ("how many
  questions are approved?"), and is consistent across counts and row lists.
- **Naive count over all version rows** — the earlier bug; over-counts and duplicates rows. Rejected.
- **A `current`/`is_latest` flag column** — would denormalize state that `MAX(version)` already
  derives, and risks drift; rejected for the POC (the `MAX(version)` read is correct and cheap).

## Consequences

- Counts shown to Medical Affairs are accurate and stable as questions are edited/re-approved.
- The `(question_id, version)` primary key makes duplicate `(id, version)` rows impossible, so the
  defensive dedup is belt-and-suspenders rather than load-bearing — but it documents intent and
  guards future query changes.
