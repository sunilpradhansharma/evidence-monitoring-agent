# Phase 1 — Data Model: Evidence Monitoring Agent POC

Entities mirror `docs/diagrams/evidence_monitor_detailed_erd.html` and the spec's Key Entities.
Storage is behind the `data_access` seam (SQLite now, Aurora/DynamoDB later). All persisted shapes
are Pydantic-validated. **No PII/PHI fields exist anywhere** (Principle III).

## Enumerations

- **ApprovalStatus**: `PENDING` | `APPROVED` | `REJECTED`
- **Persona** (question style only, not routing): `PROSPECT` | `PROVIDER` | `PATIENT`
- **Domain**: `EFFICACY` | `SAFETY` | `ACCESS` | `COMPARATIVE` | `GENERAL`
- **ResponseStatus**: `SUCCESS` | `FAILED` | `TRUNCATED` | `BLOCKED`
- **FinishReason**: `STOP` | `LENGTH` | `ERROR` | `SAFETY`
- **CompetitivePosition**: `FIRST_LINE_RECOMMENDED` | `AMONG_OPTIONS` | `SECOND_LINE` | `NOT_RECOMMENDED` | `NOT_MENTIONED`
- **CitationStatus**: `CITED` | `PARTIAL` | `ABSENT` | `WRONG_INDICATION`
- **AlertRule**: `NEGATIVE_SENTIMENT` | `NOT_RECOMMENDED` | `COMPETITOR_HIGHER` | `WRONG_INDICATION`
- **TriggerType**: `SCHEDULED` | `ADHOC`
- **AuditEventType**: `QUERY_DISPATCHED` | `RESPONSE_RECEIVED` | `RUN_STARTED` | `RUN_ENDED` | `ERROR`

## Entities

### Question  (mutable via new versions; never hard-deleted)
| Field | Type | Notes |
|-------|------|-------|
| question_id | str (PK) | stable id across versions |
| version | int | incremented on edit; history retained |
| question_text | str | generic; no PII |
| persona | Persona | authoring style tag |
| therapeutic_area | str | from data/config, not code |
| brand_focus | str | from data/config, not code |
| domain | Domain | |
| active | bool | eligible for runs when also APPROVED |
| approval_status | ApprovalStatus | default PENDING |
| approver_name | str? | set on APPROVED |
| created_at / updated_at | datetime | |

**Rules**: only `APPROVED` + `active` questions are submitted (FR-003). Edits create a new version
(FR-001). Soft-delete via `active=false`; no physical delete.

### LLMTarget  (config-sourced)
| Field | Type | Notes |
|-------|------|-------|
| target_id | str (PK) | |
| llm_name | str | e.g. openai-gpt4o |
| model_version | str | from config; never hard-coded |
| endpoint | str? | |
| temperature / max_tokens | float / int | from config |
| rpm_limit / tpm_limit | int | rate limits |
| personas | list[Persona] | which personas this target serves (Open Evidence = PROVIDER only) |
| active | bool | |
| tos_acknowledged | bool | Principle VI |

### Run
| Field | Type | Notes |
|-------|------|-------|
| run_id | str (PK) | |
| trigger_type | TriggerType | |
| started_at / ended_at | datetime | |
| questions_attempted | int | |
| responses_captured | int | |
| failure_count | int | |
| total_tokens | int | |
| est_cost | float | from `observability/cost.py` |
| last_completed_question_id | str? | resume checkpoint (Principle IX) |

### Response  (IMMUTABLE once written)
| Field | Type | Notes |
|-------|------|-------|
| response_id | uuid (PK) | |
| run_id / question_id / target_id | FK | |
| timestamp_utc | datetime | |
| llm_name / llm_model_version | str | captured at call time |
| persona / therapeutic_area / brand_focus / domain | denormalized | for queryability (FR-012) |
| response_text | str | full, unedited (DM-002) |
| response_tokens | int | |
| finish_reason | FinishReason | |
| status | ResponseStatus | SUCCESS/FAILED/TRUNCATED/BLOCKED |
| block_reason | str? | when BLOCKED |
| alert_triggered | bool | denormalized convenience flag |
| created_at | datetime | |

**Rules**: no update after insert (FR-008/FR-304); enforced in `response_repo/repository.py`.

### ScoringRecord  (versioned; one→many per Response)
| Field | Type | Notes |
|-------|------|-------|
| score_id | uuid (PK) | |
| response_id | FK | link, not mutation (FR-015) |
| version | int | re-scoring adds a version |
| sentiment_score | float | −1.0..+1.0 |
| competitive_position | CompetitivePosition | |
| citation_status | CitationStatus | WRONG_INDICATION = wrong disease/indication |
| brand_mentions | json (list[str]) | detected brands (Principle VII) |
| key_claims | json (list[str], ≤5) | |
| scoring_rationale | str | |
| scorer_model | str | from config |
| is_human_override | bool | MA override keeps AI score (FR-408/future) |
| created_at | datetime | |

### Alert  (one→many per ScoringRecord)
| Field | Type | Notes |
|-------|------|-------|
| alert_id | uuid (PK) | |
| score_id / response_id | FK | |
| rule_fired | AlertRule | |
| severity | int | WRONG_INDICATION highest |
| reason | str | human-readable trigger explanation |
| created_at | datetime | |

### AuditLog  (APPEND-ONLY)
| Field | Type | Notes |
|-------|------|-------|
| audit_id | uuid (PK) | |
| run_id | FK | |
| event_type | AuditEventType | |
| role | str | ORCHESTRATOR \| TARGET |
| target | str | target/question reference |
| ts | datetime | |
| http_status | int? | |
| detail | str | non-secret |

## Relationships

```
Question 1───* Response *───1 LLMTarget
Run      1───* Response
Run      1───* AuditLog
Response 1───* ScoringRecord
ScoringRecord 1───* Alert
```

## State Transitions

- **Question approval**: `PENDING → APPROVED` (approver recorded) | `PENDING → REJECTED` |
  `APPROVED → REJECTED`. REJECTED is terminal for runs. Editing any state creates a new version.
- **Response status** (set once at capture): `SUCCESS` | `FAILED` (after retry budget) |
  `TRUNCATED` (length cap) | `BLOCKED` (safety filter). No further transitions (immutable).
- **Run lifecycle**: started → (per question: dispatch→persist→checkpoint) → scored → evaluated →
  ended; resumable from `last_completed_question_id`.

## Validation Rules (enforced in Pydantic + repositories)

- `sentiment_score` ∈ [−1.0, +1.0]; `key_claims` length ≤ 5.
- Only `APPROVED` + `active` questions enter a run.
- `Response` rows reject any post-insert mutation.
- `ScoringRecord` always links a `response_id` and never alters the response.
- Retention: soft-delete only; minimum 24 months (FR-029).
- No field may contain PII/PHI (asserted in tests).
