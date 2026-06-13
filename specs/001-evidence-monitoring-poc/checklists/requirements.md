# Specification Quality Checklist: Evidence Monitoring Agent — POC

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-06-13
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Monitored LLM targets (GPT-4o, Gemini, Claude, conditional Open Evidence) are named as the
  *subject of monitoring* (domain scope), not as implementation stack — consistent with the
  "no implementation details" rule.
- Zero [NEEDS CLARIFICATION] markers: the conditional Open Evidence target, the "materially
  higher" competitor margin, and alert thresholds were resolved as documented Assumptions
  (configurable defaults) rather than open questions.
- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`.

---

# Requirements Quality Checklist (focus: requirements)

**Purpose**: "Unit tests for the requirements" — validate the spec's completeness, clarity,
consistency, measurability, and coverage before `/speckit.implement`. Each item tests what is
(or isn't) WRITTEN in the spec, not whether code behaves.
**Created**: 2026-06-13
**Feature**: [spec.md](../spec.md)
**Depth**: Standard · **Audience**: Reviewer (pre-implementation gate) · **Focus**: compliance,
alert/scoring measurability, immutability/audit, status & edge coverage

## Requirement Completeness

- [ ] CHK001 Are requirements defined for every response status (SUCCESS / FAILED / TRUNCATED / BLOCKED), including when each is assigned? [Completeness, Spec §FR-009]
- [ ] CHK002 Are requirements defined for all four citation_status values, including how WRONG_INDICATION is determined? [Completeness, Spec §FR-016, §FR-017]
- [ ] CHK003 Is system behavior specified when all configured targets fail for a single question? [Completeness, Spec §Edge Cases]
- [ ] CHK004 Are the enable/skip conditions for the conditional Open Evidence target fully documented? [Completeness, Spec §FR-007]
- [ ] CHK005 Are the required contents of the run summary fully enumerated? [Completeness, Spec §FR-026]
- [ ] CHK006 Is the minimum required content of each audit-log entry specified? [Completeness, Spec §FR-013]
- [ ] CHK007 Are re-scoring requirements (new version, prior versions retained, trigger) documented? [Completeness, Spec §FR-018]

## Requirement Clarity

- [x] CHK008 Is the negative-sentiment alert threshold quantified in the spec requirements, not only in supporting docs? [Clarity, Spec §FR-020] — RESOLVED: FR-020 now states default −0.3 (configurable).
- [x] CHK009 Is "materially higher" competitor sentiment quantified (≥0.3) in the requirements? [Clarity, Spec §FR-020, §Clarifications] — satisfied: FR-020 states ≥0.3.
- [x] CHK010 Is the retry budget (attempt count + backoff intervals) stated as a requirement rather than left to implementation? [Clarity, Spec §FR-010] — RESOLVED: FR-010 now states 3 attempts, 2s/4s/8s.
- [ ] CHK011 Are the query dimensions in FR-012 each defined with expected value types/ranges (e.g., sentiment range)? [Clarity, Spec §FR-012]
- [ ] CHK012 Is "soft-delete" defined with the exact fields/markers required (reason, timestamp, inactive flag)? [Clarity, Spec §FR-029]

## Requirement Consistency

- [ ] CHK013 Is "persona = question style, not routing" stated consistently across user stories and FR-004/FR-007? [Consistency, Spec §FR-004]
- [ ] CHK014 Is the single-submission-per-target decision consistent between FR-006, the Clarifications, and the ~300-call assumption? [Consistency, Spec §FR-006, §Clarifications]
- [ ] CHK015 Is "immutable response + separate versioned score" stated consistently across FR-008, FR-015, and User Story 2? [Consistency, Spec §FR-008, §FR-015]
- [ ] CHK016 Are the competitive_position and citation_status enum value sets identical everywhere they appear? [Consistency, Spec §FR-016]

## Acceptance Criteria Quality (Measurability)

- [ ] CHK017 Is SC-003's ≥95% capture rate defined with an unambiguous denominator (attempts vs questions; across vs per target)? [Measurability, Spec §SC-003]
- [ ] CHK018 Does SC-002 define what counts as an "intervention" over the 7-day unattended window? [Measurability, Spec §SC-002]
- [ ] CHK019 Is SC-004 (≥30 questions/persona across ≥2 therapeutic areas) objectively countable from the repository? [Measurability, Spec §SC-004]
- [ ] CHK020 Does SC-008 ("stakeholders confirm actionable") provide any objective acceptance signal, or is it purely subjective? [Ambiguity, Spec §SC-008]

## Scenario Coverage

- [ ] CHK021 Are resume/interrupted-run requirements defined (what state resumes, what is skipped)? [Coverage, Spec §FR-011]
- [ ] CHK022 Are requirements defined for editing an APPROVED question mid-run (version used vs new version)? [Coverage, Spec §Edge Cases]
- [ ] CHK023 Are requirements defined for empty/near-empty responses passing through scoring? [Coverage, Spec §Edge Cases]
- [ ] CHK024 Are requirements defined for the "competitor present but our therapy NOT_MENTIONED" scoring/alert path? [Coverage, Spec §Edge Cases, §FR-020]

## Edge Case Coverage

- [ ] CHK025 Are sentiment boundary conditions (−1.0, 0.0, +1.0, and the −0.3 / ≥0.3 thresholds) addressed in requirements? [Edge Case, Spec §FR-016, §FR-020]
- [ ] CHK026 Are duplicate-question handling requirements defined (distinct ids, no silent merge)? [Edge Case, Spec §Edge Cases]
- [ ] CHK027 Is the BLOCKED-vs-FAILED distinction specified as a requirement (not merely implied for Gemini safety)? [Edge Case, Spec §FR-009]

## Non-Functional Requirements

- [x] CHK028 Are performance requirements (run duration, scoring latency) captured in the spec, or only deferred to the plan/SRS? [Non-Functional, Spec §FR-030] — RESOLVED: FR-030 (≤4h run, ≤30min scoring).
- [x] CHK029 Are logging/observability and secret-redaction expectations represented as requirements in the spec? [Non-Functional, Spec §FR-031] — RESOLVED: FR-031 (structured logs + redaction).
- [x] CHK030 Are retention requirements (≥24 months, never physically purged) complete and measurable? [Non-Functional, Spec §FR-029]
- [x] CHK031 Is the startup credential preflight (present + reachable, secrets never logged) stated as a spec requirement, not only in the plan? [Non-Functional, Spec §FR-032] — RESOLVED: FR-032 (preflight).

## Dependencies & Assumptions

- [ ] CHK032 Is the assumption that Open Evidence may be deferred validated, with its impact on the ≥95% metric documented? [Assumption, Spec §Assumptions, §FR-007]
- [ ] CHK033 Is the "seed questions may be pre-approved for the P1 slice" assumption reconciled with the approval-gate requirement? [Assumption, Spec §Assumptions, §FR-003]
- [ ] CHK034 Are the external LLM provider dependencies and their terms-of-service constraints documented as requirements/assumptions? [Dependency, Spec §FR-028]

## Ambiguities & Conflicts

- [x] CHK035 Are the alert threshold defaults (negative −0.3, competitor ≥0.3) present in the spec requirements themselves, not only in quickstart/plan? [Ambiguity, Spec §FR-020] — RESOLVED: both defaults now in FR-020.
- [ ] CHK036 Is the deferred 3×-sampling option clearly marked out of scope so it cannot conflict with FR-006's single-submission rule? [Conflict, Spec §FR-006, §Clarifications]

## Notes (Requirements Quality)

- These items validate requirement quality; resolve any that fail by editing `spec.md` before implementation.
- CHK008/CHK009/CHK010/CHK035 RESOLVED (2026-06-13): alert threshold defaults (−0.3 / ≥0.3) and the
  retry budget (3 attempts, 2s/4s/8s) were promoted into FR-020 and FR-010.
- CHK028/CHK029/CHK030/CHK031 RESOLVED (2026-06-13): added FR-030 (performance), FR-031
  (observability + redaction), FR-032 (credential preflight) to the spec.
- Remaining triage: CHK020 (SC-008 subjective by design).
- FR-030 (performance) now has a proxy task T088 (concurrency + rate-limit assertion); the full
  4h-run / 30-min-scoring timing is validated operationally at the readout.
