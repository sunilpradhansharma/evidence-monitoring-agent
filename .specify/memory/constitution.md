<!--
SYNC IMPACT REPORT
==================
Version change: 1.0.0 → 1.0.1  (PATCH — source provenance corrected, no principle change)
Bump rationale: 1.0.0 ratified the 11 principles; 1.0.1 records that docs/ now holds the
correct SRS (docs/SRS.pdf), which confirms every principle.

Principles defined (11):
  I.    Human Approves, System Suggests
  II.   Immutable and Auditable
  III.  No PII/PHI
  IV.   Content-Agnostic Code
  V.    Config-Driven Targets
  VI.   Terms of Service and Data Residency
  VII.  Explain the Score
  VIII. LLM Scores, Code Decides
  IX.   Resilient and Resumable
  X.    Built to Grow into Production
  XI.   Quality Is Testable

Added sections: Additional Constraints (Stack & Boundaries); Development Workflow & Quality Gates; Governance.
Removed sections: none (template placeholders fully replaced).

Templates / artifacts status:
  ✅ CLAUDE.md — stack + golden rules aligned with these principles
  ⚠ .specify/templates/plan-template.md — Constitution Check gate not yet tailored (pending)
  ⚠ .specify/templates/spec-template.md — no mandatory-section changes identified (pending review)
  ⚠ .specify/templates/tasks-template.md — principle-driven task types (audit/versioning/coverage) pending
  ⚠ specs/001-evidence-monitoring-poc/spec.md — not yet created (forward reference in CLAUDE.md)

Source note: docs/SRS.pdf (9 pp, Evidence Monitoring Agent SRS) is the authoritative SRS and was
cross-checked against all 11 principles — every principle maps to one or more requirements
(e.g. I→BR-009/SE-002, II→FR-301/FR-304/SE-003, VII→FR-404, VIII→FR-405, IX→FR-206/NF-004,
XI→NF-013). The earlier unrelated district-manager-coaching PDF has been removed. RESOLVED.

Deferred TODOs: none blocking.
-->

# Evidence Monitoring Agent Constitution

A local proof-of-concept that monitors what public LLMs say about our therapies versus
competitors, for Medical Affairs and Commercial. These principles are non-negotiable; code,
plans, specs, and reviews MUST comply.

## Core Principles

### I. Human Approves, System Suggests
Every question MUST be reviewed and APPROVED by Medical Affairs before it can be submitted to
any LLM. The system MUST submit only questions whose `approval_status` is APPROVED. Scores and
alerts are advisory; the system MUST take no action beyond querying, recording, and surfacing —
it never contacts an HCP, publishes, or remediates on its own.
**Rationale:** Regulatory and medical accountability stays with humans; the tool informs, it
does not act.

### II. Immutable and Auditable
A `RESPONSE` record MUST be immutable once written. Derived data (sentiment, competitive
position, claims) MUST be stored as a SEPARATE, versioned `SCORING_RECORD` linked by
`response_id` — never by mutating the response. Re-scoring creates a new version; it never
overwrites. Every external LLM call MUST be written to an append-only `AUDIT_LOG`.
**Rationale:** Reproducibility, defensibility, and a complete trail of what was asked, answered,
and concluded.

### III. No PII/PHI
Questions MUST be generic and MUST NOT be seeded with real patient data. No personally
identifiable information or protected health information may be stored anywhere — code, data,
fixtures, logs, or comments.
**Rationale:** Privacy and compliance; the system has no legitimate need for personal data.

### IV. Content-Agnostic Code
Drug names, competitor names, and indications MUST live ONLY in the question repository and
config files — never hard-coded in application logic. Application code MUST remain agnostic to
the specific brands or therapeutic areas being monitored.
**Rationale:** New therapies/competitors are a data change, not a code change; prevents leakage
of regulated content into logic.

### V. Config-Driven Targets
Adding or removing an LLM target MUST be a config + adapter change, never a change to core
orchestration logic. Rate limits, parameters, and model ids MUST be externalized in config.
Model ids MUST NEVER be hard-coded.
**Rationale:** Targets evolve faster than orchestration; isolating them keeps the core stable.

### VI. Terms of Service and Data Residency
The system MUST comply with each LLM provider's terms of service. Responses MUST be stored only
in controlled local storage and MUST NOT be forwarded to third parties.
**Rationale:** Legal compliance and data custody are preconditions for operating at all.

### VII. Explain the Score
Every score MUST carry the brands it detected (`brand_mentions`), up to five key claims
(`key_claims`), and a short `scoring_rationale`. A score without its evidence is invalid.
**Rationale:** Medical Affairs must be able to judge and trust each score, not take it on faith.

### VIII. LLM Scores, Code Decides
Claude produces the structured score; whether an `ALERT` fires MUST be decided by deterministic
threshold rules in code, not by the LLM. The model never decides an action.
**Rationale:** Alerting must be predictable, auditable, and tunable independent of model behavior.

### IX. Resilient and Resumable
External API failures MUST be retried with exponential backoff. After the retry budget is
exhausted, the record MUST be marked FAILED and the run MUST continue. A run MUST be resumable
from the last completed question. The system targets **≥95% successful capture** per run.
**Rationale:** A single flaky call must never lose a run's worth of work or block other questions.

### X. Built to Grow into Production
All external dependencies MUST sit behind clean seams (`llm`, `data_access`). The local build
(SQLite + Anthropic API) MUST be able to swap to production targets (Aurora/DynamoDB + Bedrock)
by changing config and/or implementation behind those seams only — never by rewriting core
logic.
**Rationale:** The POC must be a true prototype of production, not a throwaway.

### XI. Quality Is Testable
The system MUST have pytest coverage at unit, component, and e2e levels, with **≥70% coverage on
core modules**. The **≥95% capture rate** and the **scoring-output schema** MUST be checked by
automated tests.
**Rationale:** Principles that are not enforced by tests decay; the critical guarantees must fail
the build when violated.

## Additional Constraints — Stack & Boundaries

- **Local-first:** the POC uses NO AWS services. Storage is local (SQLite/DuckDB behind a
  data-access interface).
- **Orchestration:** LangGraph with an explicit, code-defined flow — NO autonomous agent loops.
- **Claude (Anthropic API)** is the orchestrator + scorer; **Amazon Bedrock** is the documented
  production swap (config/implementation only).
- **Monitored targets** are reached via the OpenAI and Google GenAI SDKs behind the `llm` seam.
- **Secrets** MUST never be logged; `.env` is denied to tooling by project settings.

## Development Workflow & Quality Gates

- Spec-driven flow via Spec Kit: `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` →
  `/speckit-implement`. Each plan MUST include a Constitution Check that maps work to these
  principles.
- Lint/format with **ruff**; types/validation with **Pydantic**. A PostToolUse hook auto-formats
  changed Python.
- A change is not "done" until tests at the appropriate level pass and the capture-rate and
  scoring-schema checks are green.
- Reviews (human and the `constitution-guardian` subagent) MUST verify compliance before commit.

## Governance

This constitution supersedes other practices for this project. Amendments MUST be proposed with
rationale, the impact on dependent templates/specs noted, and a version bump applied.

- **Versioning:** semantic. MAJOR = incompatible principle removal/redefinition; MINOR = new or
  materially expanded principle/section; PATCH = clarifications and wording.
- **Compliance:** all PRs/plans/specs MUST verify compliance with these principles; deviations
  MUST be justified in writing or rejected.
- **Source of truth:** runtime guidance lives in `CLAUDE.md`; this file governs the principles it
  summarizes.

**Version**: 1.0.1 | **Ratified**: 2026-06-13 | **Last Amended**: 2026-06-13
