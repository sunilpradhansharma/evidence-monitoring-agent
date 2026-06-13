# ADR-0001: Spec-driven development with GitHub Spec Kit

**Status:** Accepted (2026-06-13)

## Context

This is a regulated-domain POC (Medical Affairs / Commercial) where scope, compliance, and
reviewability matter as much as the code. We needed a way to make requirements, design decisions,
and acceptance criteria explicit and reviewable *before* implementation, and to keep them traceable
afterward.

## Decision

Use **GitHub Spec Kit** to drive the project through an explicit, reviewed artifact chain:
`constitution → specify → clarify → plan → tasks → analyze → checklist → implement`. Each step
produces a versioned document under `.specify/` and `specs/001-evidence-monitoring-poc/`. The
**constitution** is the supreme document; everything downstream must comply with it.

## Options considered

- **Spec Kit (chosen)** — structured, reviewable, traceable; integrates with Claude Code skills.
- **Lightweight README + ad-hoc issues** — faster to start, but weak traceability and no
  enforced constitution/quality gates.
- **Heavyweight formal SRS only** — thorough but static; doesn't translate into an actionable,
  testable task plan or a living workflow.

## Consequences

- Strong traceability: every task and ADR maps back to a requirement and a principle.
- Up-front effort before any code, with explicit gates (clarify, analyze, checklist).
- Tooling dependency on Spec Kit and Claude Code skills.

## Open follow-up

- Keep `docs/project-status.md` updated as the living index of where the spec chain stands.
