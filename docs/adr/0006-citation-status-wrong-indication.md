# ADR-0006: Add `citation_status` with `WRONG_INDICATION` + a highest-severity alert

**Status:** Accepted (2026-06-13)

## Context

Beyond sentiment and competitive positioning, a distinct and serious failure mode is when an LLM
answers a question with content about the **wrong disease/indication** — effectively routing a
prospect, patient, or provider to information for a condition they did not ask about. This risk was
surfaced by the **GEO (generative-engine-optimization) findings deck**
(`docs/GEO-Deck-to-POC-Mapping.md`, traced source). It is not captured by a sentiment score or a
competitive-position label.

## Decision

Add a **`citation_status`** field to every `Scoring_Record` with values
`CITED | PARTIAL | ABSENT | WRONG_INDICATION`, where **`WRONG_INDICATION`** means the model
returned content for the wrong disease/indication. Add a **fourth deterministic alert rule**: a
`WRONG_INDICATION` citation status raises the **highest-severity** alert (a person routed to
wrong-disease content).

## Options considered

- **Dedicated `citation_status` + highest-severity alert (chosen)** — makes the wrong-indication
  failure explicit, scorable, and alertable.
- **Fold it into `sentiment_score`** — loses the signal; a wrong-indication answer can still read
  as positive.
- **Track it only in free-text rationale** — not queryable, not alertable, not testable.

## Consequences

- Scoring schema, data model, alert rules, and severity ordering all include the new field/rule.
- The highest-severity alert ensures wrong-indication responses surface first to Medical Affairs.

## Open follow-up

- Locate/restore `docs/GEO-Deck-to-POC-Mapping.md` in the repo and cross-link the specific GEO
  findings that motivated this decision.
- Validate the scorer's `WRONG_INDICATION` precision/recall against reviewed examples during the
  readout.
