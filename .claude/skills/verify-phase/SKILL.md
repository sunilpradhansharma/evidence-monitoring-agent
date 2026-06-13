---
name: verify-phase
description: Lint with ruff then run the pytest suite, and print a short PASS/FAIL summary with what remains.
user-invocable: true
disable-model-invocation: true
allowed-tools: Bash, Read
---

# verify-phase

Run the quality gate for the current phase and summarize.

## Lint
!`uv run ruff check .`

## Tests
!`uv run pytest -q`

## Your task
Read the two command outputs above and print a tight summary — nothing else:

```
Lint:  PASS | FAIL (N issues)
Tests: PASS | FAIL (P passed, F failed)

Remaining:
- <first ruff issue: file:line — rule>
- <first failing test id — first assertion>
```

If both pass, print `Lint: PASS / Tests: PASS — phase verified.` and stop.
Do **not** fix anything; only report.
