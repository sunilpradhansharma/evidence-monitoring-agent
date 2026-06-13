---
name: import-question-bank
description: Idempotently import the approved question bank from data/question_bank.csv into the question repository as PENDING (FR-102 schema), reporting counts per persona and therapeutic area.
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(uv run:*), Bash(sqlite3:*)
---

# import-question-bank

Import the approved question bank into the question repository.

## Source & schema
- **Source**: `data/question_bank.csv` (the approved bank — brand/competitor names live ONLY
  here as data, never in code).
- **Target FR-102 schema** (per row): `question_id`, `persona`, `therapeutic_area`,
  `brand_focus`, `domain`, `approval_status`, `active`, `question_text`.

## Rules
1. Insert each row with `approval_status = PENDING`.
2. **Idempotent**: upsert keyed on `question_id` — re-running updates the existing row, never
   creates a duplicate.
3. Preserve `active` from the source if present; otherwise default to the project convention.
4. Do not invent or hard-code any brand/competitor/indication values — they come only from the CSV.

## Steps
- Prefer the project's existing importer (look under `question_repo/`, `scripts/`, or a
  `uv run` entrypoint). If one exists, run it. If not, perform the upsert directly against the
  question repository / SQLite DB using the schema above.
- After import, report:
  ```
  Imported/updated: N rows (X new, Y updated)
  By persona:           <persona>: count ...
  By therapeutic area:  <area>: count ...
  ```

Stop after reporting. Make no changes outside the question repository.
