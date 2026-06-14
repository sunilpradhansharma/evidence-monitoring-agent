# ADR-0007: Offline, deterministic e2e capture-rate gate + CLI credential preflight

**Status:** Accepted (2026-06-13)

## Context

Two constitution guarantees needed an enforceable home as the build closed out:

- **≥95% successful capture** (Principle IX / SC-003) — a number that decays unless a test fails
  the build when it is missed.
- **Secrets never logged + nothing submitted without credentials** (Principle VI / FR-032) — the
  `/health` endpoint already shared a presence-only `credential_preflight`, but the **CLI** `run`/
  `subset` live path did not gate on it, so a live run with a missing key could reach a target
  before failing. The plan's "Startup Credential Preflight" section requires `cli.py` to preflight
  before any query.

The capture-rate test must run in CI with no API keys and no network, and must be reproducible.

## Decision

- **Offline e2e suite (`tests/e2e/`).** Run the whole pipeline — import the real seed bank →
  approve → dispatch → score → alert → render — in deterministic OFFLINE/MOCK mode. Assert one
  immutable response per (APPROVED question × eligible target), **≥95% capture** (including a
  flaky-target case whose retry budget is exhausted on a small deterministic fraction and still
  clears the bar), versioned scores carrying their evidence, resume-without-duplicates, and that
  the self-contained dashboard plus CSV/JSON exports are produced. Per-target rate limiting is
  disabled in these tests (it has its own unit test) so a full-seed run needs no wall-clock sleeps.
- **CLI credential preflight.** A live `run`/`subset` calls `preflight_or_error` (wrapping the
  shared `credential_preflight`) **before** opening the store or dispatching: a missing required
  key prints a clear, non-secret error naming only the env var and exits non-zero, submitting
  nothing. Resolved keys are registered with the redacting logger. `--mock` runs skip the gate
  (fully offline).
- **`import-questions` CLI command.** Promoted to a first-class subcommand (idempotent upsert as
  PENDING) so the documented quickstart seed step is real, not just a skill.

## Options considered

- **Offline mock e2e + CLI preflight (chosen)** — deterministic, keyless, CI-friendly; the gate
  lives in code and matches `/health`.
- **Live-API e2e** — exercises real providers but is flaky, slow, costs money, and cannot run in
  CI; rejected for the capture-rate gate (live runs remain a manual readout step).
- **Preflight only on `/health`** — leaves the CLI live path ungated, contradicting FR-032; rejected.

## Consequences

- The ≥95% capture guarantee and the no-submit-without-credentials rule now fail the build when
  violated.
- e2e tests depend on the seed CSV shape and the adapter mock behaviours; both are stable contracts.
- Disabling rate limiting in e2e means cadence/timing is validated elsewhere (the dedicated
  rate-limit unit test and the deferred performance proxy, Impl-9).
