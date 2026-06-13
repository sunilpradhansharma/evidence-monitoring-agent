---
name: add-llm-target
description: Add a new LLM target — config entry, adapter implementing the base protocol (retry/backoff + offline mock), and a unit test. Takes the target name as an argument.
argument-hint: <target-name>
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(uv run pytest:*), Bash(uv run ruff:*)
---

# add-llm-target

Add a new LLM target named **$ARGUMENTS** end to end. If `$ARGUMENTS` is empty, ask for the name and stop.

## Steps
1. **Config** — add a `$ARGUMENTS` entry to `config/targets.yaml` with: `model_version`,
   `params` (temperature, max_tokens, etc.), `rate_limits` (rpm/tpm), and `personas`.
   The model id lives here — never in code.
2. **Adapter** — create `llm/adapters/$ARGUMENTS.py` implementing the base adapter protocol
   (read `llm/adapters/base.py` first and match its interface). Include:
   - retry with exponential backoff on transient failures,
   - an **offline mock mode** that returns canned responses with no network call,
   - reading the model id and settings from config, not literals.
3. **Test** — add `tests/adapters/test_$ARGUMENTS.py` exercising the adapter in mock mode
   (happy path + one retry path). Run `uv run pytest -q tests/adapters/test_$ARGUMENTS.py`.

## Constraints (enforce, do not violate)
- **No core orchestration changes** — touch only `config/`, `llm/adapters/`, and `tests/`.
- **Model id from config** — no hard-coded model ids or endpoints in the adapter.
- **ToS reminder** — end your summary with: "⚠️ Confirm this provider's Terms of Service
  permit this usage before enabling the target in production."

Report the files created/modified and the test result.
