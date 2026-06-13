---
name: scoring-schema-check
description: Validate the scorer's JSON output against the spec schema and report any drift in fields or types.
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash(uv run:*), Bash(sqlite3:*)
---

# scoring-schema-check

Validate scorer output against the spec schema and report drift. Read-only.

## Expected schema
The scorer's JSON must contain exactly these top-level fields:
- `sentiment_score`
- `competitive_position`
- `citation_status`
- `brand_mentions`
- `key_claims`
- `scoring_rationale`

## Steps
1. Locate the scorer output to validate — recent stored scores (DB / output dir) and/or the
   schema definition the code declares. Prefer real produced output over a static fixture.
2. Compare actual fields against the expected set. Report:
   - **Missing** fields (in spec, absent in output)
   - **Extra** fields (in output, not in spec)
   - **Type/shape drift** (e.g. `sentiment_score` not numeric, `key_claims` not a list)
3. Output:
   ```
   Schema: PASS | DRIFT
   Missing:  <fields or none>
   Extra:    <fields or none>
   Type drift: <field: expected vs actual, or none>
   ```

Report only. Do not modify the scorer, schema, or stored output.
