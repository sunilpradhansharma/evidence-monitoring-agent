# Project Status — Evidence Monitoring Agent (POC)

> **Living memory.** Update this file as work progresses — it is the single place to learn where
> the project stands, what was decided and why, what's still open, and how to pick the work back
> up. Keep the roadmap checkboxes and commit hashes current.

**Last updated:** 2026-06-13

## Project summary

A local, spec-driven POC that monitors how public LLMs (OpenAI GPT-4o, Google Gemini, Anthropic
Claude, + conditional Open Evidence) represent AbbVie therapies versus competitors. It captures
and scores only; a human approves every question before submission. Built for Medical Affairs and
Commercial. See [README.md](../README.md) and [technical-architecture.md](technical-architecture.md).

## Current status

**Implementation essentially complete; POC readout/acceptance is the remaining step.** The full
spec-driven chain (constitution → spec → clarify → plan → tasks → analyze → checklist) is done and
committed, and the application is built end-to-end per [`tasks.md`](../specs/001-evidence-monitoring-poc/tasks.md):
foundational seams → capture & store → scoring → approval gate → deterministic alerts → dashboard +
reports + `/health`, with the scheduler, CLI, cost/budget accounting, and an offline e2e suite.

- **Pipeline runs offline:** `evidence-monitor run --mock` executes the whole capture → score →
  alert flow with no keys or network; `tests/e2e/` asserts **≥95% capture** over the full seed
  bank (including a flaky-target case) and that the self-contained dashboard + CSV/JSON exports are
  produced.
- **Hardening in place:** structured JSON logs with secret redaction; a **startup credential
  preflight** on the live CLI `run`/`subset` path and `GET /health` (missing key → clear,
  non-secret error, nothing submitted); ≥70% coverage on core modules (overall ~91%).
- **Question bank:** 162 questions present (`data/question_bank.csv`) — Patient 59 · Prospect 49 ·
  Provider 54, across Immunology / Neuroscience / Oncology. **All PENDING** (none approved → none
  submittable yet); import + approve via the CLI (`import-questions`, `approve`) or the Approvals UI.
- **Acceptance targets:** 7-day unattended run, zero interventions; ≥95% capture; ≥30
  questions/persona across ≥2 therapeutic areas.

## Phase roadmap

Legend: ✅ done · 🟡 in progress · ⬜ not started. "Verify" = the phase's review/validation gate.

| Phase | Description | Verify | Status | Commit |
|-------|-------------|--------|--------|--------|
| 0 | Bootstrap repo + Spec Kit init + Claude Code scaffolding | Repo builds; skills/agents/hooks present | ✅ | `dcf039c`, `58b61e0` |
| 1 | Constitution (11 principles) | All 11 ratified; v1.0.1 | ✅ | `07e78a5` |
| 2 | Specify (feature spec) | Spec quality checklist passes | ✅ | `867a6ec` |
| 3 | Clarify (resolve ambiguities) | 0 open clarifications | ✅ | `001d649` |
| 4 | Plan (architecture, data-model, contracts) | Constitution Check PASS (pre + post) | ✅ | `dbae1da` |
| 5 | Tasks (dependency-ordered breakdown) | 88 tasks, all traceable | ✅ | `c9b86ce` |
| 6 | Analyze + Checklist (consistency + requirements quality) | 0 CRITICAL; gaps remediated | ✅ | `b56cdad`, `48e5992` |
| 7 | Documentation (README, architecture, status, ADRs) | This set written & reviewed | ✅ | `ebeb648`, `b53b791` |
| 8 | Implementation (build per tasks.md) | All Impl rows below complete | 🟡 | see rows |

### Implementation sub-phases (Phase 8)

Rows are grouped by user story; the delivering commit(s) are listed. (Commit messages carry their
own `Impl-N` labels in build order, which differ from these planning rows.)

| Step | Description | Tasks | Status | Commit |
|------|-------------|-------|--------|--------|
| Impl-1 | Setup (package, deps, tooling) | T001–T004 | ✅ | `d28cfc5` |
| Impl-2 | Foundational seams (data_access, SQLite, schemas, audit, seed) | T005–T020 | ✅ | `499f562` |
| Impl-3 | US1 — capture & store (adapters, run, resume) 🎯 MVP | T021–T048 | ✅ | `bbb0dd8`, `b3d5730`, `65be66f`, `5a65974` |
| Impl-4 | US2 — scoring (structured, versioned) | T049–T055 | ✅ | `3b3636d`, `31e22ae` |
| Impl-5 | US3 — question curation & approval gate | T056–T063 | ✅ | `3a273b1`, `a86aec2` |
| Impl-6 | US4 — deterministic alerts | T064–T069 | ✅ | `65be66f` |
| Impl-7 | US5 — dashboard, reports, run summary, /health | T070–T078 | ✅ | `2e3e948`, `68085a1` |
| Impl-8 | Retention / soft-delete (`deactivate`, never purge) | T086–T087 | ✅ | `499f562` |
| Impl-9 | Performance proxy (concurrency / rate-limit timing) | T088 | ⬜ | _deferred to readout_ |
| Impl-10 | Polish & cross-cutting (e2e, capture-rate, coverage, preflight, docs) | T079–T085 | 🟡 | _this session (uncommitted)_ |
| Impl-11 | POC readout / acceptance validation | — | ⬜ | |

## Decisions log

- **The SRS defines scope.** `docs/SRS.pdf` ("Evidence Monitoring Agent — POC") is the
  authoritative scope. Principles and tasks trace back to it. (Note: an earlier mis-filed PDF was
  replaced with the correct SRS.)
- **Persona → LLM table is examples, not routing.** Personas (Prospect/Provider/Patient) are
  *question-authoring styles*. Every approved question goes to every configured target; the only
  routing rule is the conditional **Open Evidence = Provider-only**.
- **Local-first with a production swap.** Build locally (SQLite + Anthropic API); production swaps
  to Aurora/DynamoDB + Bedrock + EventBridge behind the `llm` and `data_access` seams. (ADR-0002)
- **Combined local-only UI, approver-name, no RBAC.** One FastAPI app serves read-only Reports and
  read-write Approvals; approvals record an `approver_name`; no authentication/RBAC in the POC.
  (ADR-0005)
- **`citation_status` / `WRONG_INDICATION` folded in.** Scoring includes `citation_status`
  (`CITED/PARTIAL/ABSENT/WRONG_INDICATION`); `WRONG_INDICATION` (a person routed to wrong-disease
  content) raises the highest-severity alert. Traced to the AbbVie GEO findings. (ADR-0006)
- **LLM scores, code decides alerts.** Four deterministic rules in code; the model never decides
  an alert. (ADR-0003)
- **Immutable responses + versioned scores.** Responses are write-once; scores are separate
  versioned records. (ADR-0004)
- **Single submission per question/target/run**, 24-month retention via soft-delete, alert
  defaults (negative −0.3, competitor ≥0.3), retry budget (3 attempts, 2s/4s/8s) — set during
  `/speckit.clarify` and the analysis remediation.
- **Offline, deterministic e2e + capture-rate gate.** The ≥95% capture guarantee is enforced by an
  e2e suite that runs the whole pipeline over the seed in mock mode (no keys/network), including a
  flaky-target case that still clears the bar. The CLI `run`/`subset` live path runs the same
  credential preflight as `/health` (missing key → clear non-secret error, nothing submitted), and
  `import-questions` is now a first-class CLI command. (ADR-0007)

## Stakeholder facts

- **Requested by:** Medical Affairs & Commercial (SRS author: Nisha Paliwal).
- **Primary users:** Medical Affairs (curate + approve questions, review findings) and Commercial
  (review competitive positioning).
- **Audiences for output:** the POC readout dashboard.
- **Therapeutic areas in the bank:** Immunology, Neuroscience, Oncology.

## Open items

- [ ] **Medical Affairs approval** of the 162-question bank (all currently PENDING; none
  submittable until approved).
- [ ] **Legal / ToS sign-off** confirming automated querying is permitted for each LLM provider
  (Constitution VI; SRS SE-005).
- [ ] **Open Evidence API access** — confirm before it's needed; otherwise it stays deferred and
  does not count against the ≥95% capture target.
- [ ] **Pin the model id** for the Claude orchestrator/scorer in config. The SRS names an
  Opus-class model; the exact id must be pinned and confirmed (model ids are never hard-coded).
- [ ] Locate / restore `docs/GEO-Deck-to-POC-Mapping.md` (referenced by ADR-0006 but not present
  in the repo).
- [ ] Add the `evidence_monitor_module_architecture` diagram (listed but not yet in `docs/diagrams/`).

## How to resume

1. Read this file, then [README.md](../README.md) and
   [technical-architecture.md](technical-architecture.md).
2. Check the **Phase roadmap** for the first ⬜ / 🟡 row and its tasks in
   [`tasks.md`](../specs/001-evidence-monitoring-poc/tasks.md).
3. Confirm you're on branch `001-evidence-monitoring-poc` (`git status` clean) and synced with
   `origin`.
4. Sanity-check the build offline: `uv sync && uv run pytest -q` (full suite, offline) and
   `uv run evidence-monitor run --mock` (whole pipeline, mocked). The remaining open items are the
   **performance proxy** (Impl-9) and the **POC readout / acceptance validation** (Impl-11).
5. After each phase's Verify passes, update the roadmap status + commit hash here, and append any
   new decision to the log; let the `constitution-guardian` and `content-agnostic-auditor`
   subagents check staged changes before commit.
