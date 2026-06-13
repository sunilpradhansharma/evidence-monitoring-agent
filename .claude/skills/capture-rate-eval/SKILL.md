---
name: capture-rate-eval
description: Run the full pipeline in mock mode over the seed data, compute the successful-capture rate, and report whether it meets the ≥95% target.
user-invocable: true
disable-model-invocation: true
context: fork
allowed-tools: Read, Glob, Grep, Bash(uv run:*)
---

# capture-rate-eval

Evaluate the successful-capture rate of the pipeline. Runs in a forked subagent to keep the
main context clean.

## Steps
1. Run the full pipeline in **mock mode** over the seed dataset (no live LLM / network calls).
   Use the project's pipeline entrypoint via `uv run` (look for a `--mock`/`--offline` flag or
   a mock config). Do not modify any source or seed data.
2. Compute the **successful-capture rate** = captured / total attempted over the seed.
3. Report:
   ```
   Capture rate: 96.4% (Captured C / Total T)
   Target ≥95%:  MET | NOT MET
   ```
   If NOT MET, list the top buckets (persona / therapeutic area) where captures failed.

Report only the result. Make no changes to the repo.
