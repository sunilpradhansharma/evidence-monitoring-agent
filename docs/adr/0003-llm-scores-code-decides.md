# ADR-0003: LLM scores; deterministic code decides alerts

**Status:** Accepted (2026-06-13)

## Context

The system scores LLM responses (sentiment, competitive position, citation status) and raises
alerts on concerning answers. Alerts drive scarce Medical Affairs attention, so they must be
predictable, auditable, reproducible, and tunable — independent of model behavior.

## Decision

Split the two responsibilities:

- **Claude scores.** The scorer returns a structured, schema-validated object (sentiment,
  competitive position, citation status, brands, key claims, rationale).
- **Code decides alerts.** `alerts/rules.py` applies **four deterministic threshold rules** in
  code. The model never decides whether an alert fires. Identical inputs always produce identical
  alert outcomes. Thresholds (e.g., negative −0.3, competitor ≥0.3) come from config.

## Options considered

- **LLM scores + code decides (chosen)** — deterministic, auditable, tunable.
- **LLM decides alerts directly** — simplest prompt, but non-deterministic, hard to audit, and
  violates Constitution VIII.
- **Pure rule-based scoring (no LLM)** — fully deterministic but can't judge nuanced free-text
  sentiment/positioning.

## Consequences

- Alert logic is unit-testable at the boundaries and reproducible.
- Two stages to maintain (scoring prompt + rules), kept deliberately separate (separate tasks).
- Threshold tuning is a config change, not a code/model change.

## Open follow-up

- Validate default thresholds against real scored data during the readout; adjust in config.
