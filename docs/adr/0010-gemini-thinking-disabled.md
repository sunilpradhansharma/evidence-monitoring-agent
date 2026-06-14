# ADR-0010: Disable Gemini "thinking" and pin a current model id (config + adapter, not core)

**Status:** Accepted (2026-06-14)

## Context

During live bring-up, the Google Gemini target produced a cluster of `TRUNCATED` responses while
the OpenAI and Anthropic targets completed normally at the same `max_tokens`. The configured model
is a **thinking model** (`gemini-2.5-flash`): its internal "thinking" tokens are billed as output
and count against `max_output_tokens`, so a budget sized for a visible answer was consumed by
hidden reasoning, cutting the answer off at the token limit → `finish_reason = MAX_TOKENS` →
`TRUNCATED`. The other two targets, queried without a thinking budget, were unaffected.

For this evidence-monitoring use case the value is the model's **public-facing answer** (what it
tells a prospect/patient/provider), not its private reasoning — so paying for thinking tokens both
costs more and was the direct cause of the truncation.

## Decision

A **config + adapter** change only (Principle V/X — core orchestration untouched):

- **Disable Gemini thinking** in the adapter: `llm/adapters/gemini.py` passes
  `thinking_config=types.ThinkingConfig(thinking_budget=0)` in the `GenerateContentConfig`, so the
  whole output budget goes to the visible answer, matching the other targets and keeping cost flat.
- **Modest `max_tokens` headroom**: `config/targets.yaml` sets the `google-gemini` target's
  `max_tokens` to `2048` (belt-and-suspenders for genuinely long answers; the other two targets
  remain at `1024`).
- **Model ids stay in config.** As verified at the time of writing, the active targets in
  `config/targets.yaml` are `openai-gpt4o` → `gpt-4o-2024-08-06`, `google-gemini` →
  `gemini-2.5-flash`, and `anthropic-claude-target` → `claude-sonnet-4-6`. These are config values,
  never hard-coded, and remain subject to the open "pin/confirm the exact model ids" item before any
  real deployment.

The `TRUNCATED` handling itself is unchanged: a length-capped reply still preserves the full
captured (partial) text and is still scored — disabling thinking simply makes truncation rare for
Gemini rather than systematic.

## Options considered

- **Disable thinking + modest token bump (chosen)** — fixes truncation on the merits (we score the
  answer, not the reasoning) and keeps cost flat.
- **Only raise `max_output_tokens`** — would also reduce truncation but pays for thinking tokens
  plus a longer answer; more expensive for no analytical benefit.
- **Switch to a non-thinking Gemini model** — viable, but the thinking-off config achieves the same
  with the current model id and is reversible from config.

## Consequences

- Gemini answers complete like the other targets; cost stays comparable.
- This is a behavior change to one provider adapter behind the `llm` seam — no change to capture,
  scoring, alerts, orchestration, or the data layer.
- Model ids and the thinking setting remain config/adapter concerns; production must still pin and
  ToS-clear the exact provider model ids.
