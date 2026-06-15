# ADR-0013: Explicit target `kind` classification field (replacing the persona-count heuristic)

**Status:** Accepted (2026-06-14)

## Context

The dashboard needs to classify each monitored target — to label it, order it, and decide how it is
presented — and to distinguish a general-purpose public LLM from a literature-synthesis target and
from a real commercial provider API.

An earlier implementation **inferred** this from how many personas a target served: a target serving
all personas was treated as a "full LLM", and a target serving a subset (Provider-only) was treated
as a limited/secondary target and, by default, de-emphasized or excluded. This was a fragile proxy:
persona coverage is not the same fact as "what kind of system is this". In particular, a real
provider-only product (e.g. Open Evidence) would have been mislabeled as a limited/dev target and
dropped from the default view — exactly the wrong, dishonest outcome.

## Decision

- **Add an explicit `kind` field to the target config** (`config/targets.yaml` → `LLMTarget.kind`),
  with values `llm` (a general-purpose public LLM), `synthesis` (a literature-synthesis target), and
  `provider-api` (a real commercial clinical provider API). Targets may also set an explicit
  `display_name`. Both are **config facts**, consistent with Principle V (config-driven targets).
- **Classify and label by `kind`, not by persona count.** `render.target_metas` reads `kind` +
  `display_name` directly from config; there is **no persona-count heuristic**. All kinds are
  **first-class** in the dashboard (no kind is hidden or excluded by default); `kind` only groups and
  orders chart series.
- **One source of truth for the frontend.** `GET /api/targets` serves each target's `kind` +
  `display_name`; the React app labels and classifies every target by name from that endpoint — no
  target slug or display string is hard-coded client-side.
- Names that are not present in config default to `kind: llm` with the raw name as the label.

## Options considered

- **Explicit config `kind` field (chosen)** — honest, stable, content-agnostic; classifies by an
  intended fact rather than an inferred proxy; correctly distinguishes LLM vs synthesis vs a future
  provider API.
- **Keep inferring from persona coverage** — rejected; it conflates "serves Provider only" with
  "is a dev/limited target" and would mislabel a real provider-only product.
- **Hard-code the classification in the frontend** — rejected; it would put target identity in two
  places (drift risk) and violate the single-source-of-truth goal.

## Consequences

- Targets are classified by an explicit, reviewable config field; adding/retyping a target stays a
  config change. The real Open Evidence target, when activated, is correctly treated as a production
  provider (`kind: provider-api`), not a dev/limited target.
- The frontend has no embedded knowledge of any specific target; labels come from the backend.
- `kind` is presentation/classification only — it never affects capture, scoring, or alert logic.

## Open follow-up

- None. If future kinds are needed (e.g. an internal model class), they are a config + small
  presentation change.
