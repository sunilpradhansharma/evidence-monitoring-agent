# Project Status — Evidence Monitoring Agent (POC)

> **Living memory.** Update this file as work progresses — it is the single place to learn where
> the project stands, what was decided and why, what's still open, and how to pick the work back
> up. Keep the roadmap checkboxes and commit hashes current.

**Last updated:** 2026-06-14

## Project summary

A local, spec-driven POC that monitors how public LLMs represent the sponsor's therapies versus
competitors, for Medical Affairs and Commercial. Three public models are queried as configured
targets — **OpenAI GPT-4o, Google Gemini, and Anthropic Claude** (Claude is also the orchestrator +
scorer) — with a fourth, **Open Evidence**, defined as a conditional Provider-only target that is
**inactive** pending real API access and ToS review. The system captures and scores only; a human
approves every question before submission. See [README.md](../README.md) and
[technical-architecture.md](technical-architecture.md).

## Current status

**Implementation complete and committed; the POC readout / acceptance validation is the remaining
step.** The full spec-driven chain (constitution → spec → clarify → plan → tasks → analyze →
checklist) is done, and the application is built end-to-end: foundational seams → capture & store →
scoring → approval gate → deterministic alerts → dashboard + reports + `/health`, plus the
scheduler, CLI, cost/budget accounting, an offline e2e suite, a **React dashboard**, and a
**read-only `/api` JSON layer**.

- **Pipeline runs offline:** `evidence-monitor run --mock` executes the whole capture → score →
  alert flow with no keys or network; `tests/e2e/` asserts **≥95% capture** over the full seed
  bank (including a flaky-target case) and that the dashboard + CSV/JSON exports are produced.
- **Live bring-up done:** real model ids are set in config, the `health-check` does a genuine
  per-active-target round-trip (inactive targets are SKIPped, never reported live), and live
  runs/smoke tests print per-response capture + scoring confirmation with non-secret failure
  diagnostics.
- **React dashboard (primary UI):** a Vite + TypeScript + Tailwind SPA (Recharts, Inter) served by
  FastAPI at `http://127.0.0.1:8000`, backed by read-only `/api/*` endpoints that reuse the existing
  `render.py` aggregation. The original server-rendered UI is retained at `/html`. (ADR-0008)
- **Version-aware question counts:** all counts/lists use the latest version per `question_id`,
  fixing an earlier over-count over the immutable version history. (ADR-0009)
- **Gemini truncation fixed:** thinking disabled (`thinking_budget=0`) + a modest `max_tokens` bump,
  so Gemini answers complete like the other targets. (ADR-0010)
- **Hardening in place:** structured JSON logs with secret redaction; a **startup credential
  preflight** on the live CLI `run`/`subset` path and `GET /health`; ≥70% coverage on core modules
  (overall ~91%).
- **Question bank:** 162 questions in `data/question_bank.csv` (Patient 59 · Prospect 49 · Provider
  54), across the Immunology / Neuroscience / Oncology therapeutic areas. The bank **imports as
  PENDING**; approval (CLI or the Approvals tab) gates submission. (Local demo DBs may have a subset
  approved for readouts.)

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
| 8 | Implementation (build per tasks.md) | All Impl rows below complete | ✅ | see rows |
| 9 | POC readout / acceptance validation | 7-day unattended run; stakeholder sign-off | ⬜ | |

### Implementation sub-phases (Phase 8)

| Step | Description | Status | Commit |
|------|-------------|--------|--------|
| Impl-1 | Setup (package, deps, tooling) | ✅ | `d28cfc5` |
| Impl-2 | Foundational seams (data_access, SQLite, schemas, audit, seed) | ✅ | `499f562` |
| Impl-3 | US1 — capture & store (adapters, run, resume) 🎯 MVP | ✅ | `bbb0dd8`, `b3d5730`, `65be66f`, `5a65974` |
| Impl-4 | US2 — scoring (structured, versioned) | ✅ | `3b3636d`, `31e22ae` |
| Impl-5 | US3 — question curation & approval gate | ✅ | `3a273b1`, `a86aec2` |
| Impl-6 | US4 — deterministic alerts | ✅ | `65be66f` |
| Impl-7 | US5 — dashboard, reports, run summary, /health | ✅ | `2e3e948`, `68085a1` |
| Impl-8 | Retention / soft-delete (`deactivate`, never purge) | ✅ | `499f562` |
| Impl-9 | Polish & cross-cutting (e2e, capture-rate, coverage, preflight, docs) | ✅ | `fa06cb8` |
| Impl-10 | Live bring-up (real model ids, honest health-check, per-failure diagnostics) | ✅ | `9282a7e` |
| Impl-11 | React + Tailwind dashboard + read-only `/api`; version-aware counts; Gemini fix; Inter font | ✅ | `89f12cb`, `1707028`, `7e428ec` |
| Perf | Performance proxy (concurrency / rate-limit timing) | ⬜ | _deferred to readout_ |

## Decisions log

- **Local-first with a production swap.** Build locally (SQLite + Anthropic API); production swaps
  to Aurora/DynamoDB + Bedrock + EventBridge behind the `llm` and `data_access` seams. (ADR-0002)
- **LLM scores, code decides alerts.** Four deterministic rules in code; the model never decides an
  alert. (ADR-0003)
- **Immutable responses + versioned scores.** Responses are write-once; scores are separate
  versioned records. (ADR-0004)
- **Single local-only app, approver-name, no RBAC.** Reports are read-only; the only writes are
  approvals, which record an `approver_name`. (ADR-0005; UI-rendering portion superseded by ADR-0008)
- **`citation_status` / `WRONG_INDICATION`.** Scoring includes `citation_status`
  (`CITED/PARTIAL/ABSENT/WRONG_INDICATION`); `WRONG_INDICATION` (a person routed to wrong-disease
  content) raises the highest-severity alert. Traced to the GEO analysis findings. (ADR-0006)
- **Offline, deterministic e2e + capture-rate gate** and a CLI credential preflight matching
  `/health`. (ADR-0007)
- **React SPA primary UI + read-only `/api` reusing `render.py`.** No new aggregation; writes stay
  on the existing audited approval endpoints; legacy HTML kept at `/html`. (ADR-0008)
- **Version-aware question counts** — latest version per `question_id` everywhere. (ADR-0009)
- **Gemini thinking disabled + current model id** (config + adapter only) to stop truncation. (ADR-0010)
- **Single submission per question/target/run**, 24-month retention via soft-delete, alert defaults
  (negative −0.3, competitor ≥0.3), retry budget (3 attempts, 2s/4s/8s) — set during clarify/analysis.

## What is fully built and working

- The **3-LLM capture pipeline** (OpenAI GPT-4o, Google Gemini, Anthropic Claude) with retry/backoff,
  rate limiting, four capture statuses (SUCCESS/FAILED/TRUNCATED/BLOCKED), resume, and audit logging.
- **Scoring** (structured, versioned, explainable) and the **four deterministic alert rules**,
  including the highest-severity `WRONG_INDICATION` rule.
- The **React dashboard** (run selector, headline, metric cards, coverage heatmap, sentiment chart,
  citation panel, positioning table, alerts, response drill-down) and the **approval workflow**
  (reviewer-name gate, persona-grouped pending queue, read-only approved/rejected tables).
- The **append-only audit log**, structured logging with secret redaction, cost/token accounting,
  the scheduler, the CLI, and the offline e2e + capture-rate gate.

## Pending / not built

- **Open Evidence real integration** — defined as a conditional Provider-only target but **inactive**
  (`active: false`, `tos_acknowledged: false`, placeholder model id) pending real enterprise API
  access and Legal/ToS review. Its absence does not count against the ≥95% capture target. *(No
  separate dev/reference target exists in config; none is implied.)*
- **In-UI question authoring** — questions are imported from CSV/Excel and approved in the UI/CLI;
  there is **no in-app form to create/edit question text** in the React UI (edit exists as a POST
  endpoint but is not surfaced in the SPA).
- **Upstream question feeds** — no automated ingestion from an external question source; curation is
  a manual CSV import.
- **Performance proxy** — the concurrency / rate-limit timing validation is deferred to the readout.
- **Restore `docs/GEO-Deck-to-POC-Mapping.md`** — referenced by ADR-0006 but not present in the repo.
- **Add the `evidence_monitor_module_architecture` diagram** — listed but not yet in `docs/diagrams/`.

## Human gates before a real deployment

These are people decisions, not code, and they block live operation:

- **Medical Affairs approval** of the question bank (it imports as PENDING; nothing is submittable
  until approved). The CLI `approve-all-test-numbered` helper is **for testing only**, not MA sign-off.
- **Legal / ToS sign-off** confirming automated querying is permitted for each LLM provider
  (Constitution VI). `tos_acknowledged` is set per target in config and must reflect a real review.
- **Pin & confirm the exact model ids** for every target and for the Claude orchestrator/scorer
  (model ids are config values, never hard-coded; current values are listed in ADR-0010).

## Stakeholder facts

- **Requested by / primary users:** Medical Affairs (curate + approve questions, review findings)
  and Commercial (review competitive positioning).
- **Audience for output:** the POC readout dashboard.
- **Therapeutic areas in the seed bank:** Immunology, Neuroscience, Oncology.

## How to resume

1. Read this file, then [README.md](../README.md) and [technical-architecture.md](technical-architecture.md).
2. Confirm you're on branch `001-evidence-monitoring-poc` and synced with `origin`.
3. Sanity-check offline: `uv sync && uv run pytest -q` (full suite, offline) and
   `uv run evidence-monitor run --mock` (whole pipeline, mocked).
4. To view the dashboard: `cd frontend && npm install && npm run build && cd ..`, then
   `uv run uvicorn evidence_monitor.api:app` → `http://127.0.0.1:8000`.
5. The remaining work is the **POC readout / acceptance validation** (7-day unattended run, ≥95%
   capture, stakeholder sign-off) and the deferred **performance proxy**.
6. Let the `constitution-guardian` and `content-agnostic-auditor` subagents check staged changes
   before commit; update this file's roadmap + decisions as work lands.
