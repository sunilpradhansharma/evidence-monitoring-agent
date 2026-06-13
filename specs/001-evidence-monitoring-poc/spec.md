# Feature Specification: Evidence Monitoring Agent — POC

**Feature Branch**: `001-evidence-monitoring-poc`

**Created**: 2026-06-13

**Status**: Draft

**Input**: User description: "An automated assistant that, on a daily schedule, asks a curated
bank of approved questions to several public LLMs, captures every response as a queryable
record, scores each response for brand sentiment and competitive positioning, flags concerning
responses, and presents the findings on a simple dashboard for Medical Affairs and Commercial."

## User Scenarios & Testing *(mandatory)*

The system serves **Medical Affairs** and **Commercial** stakeholders who need to know what
public LLMs tell prospects, patients, and providers about our therapies versus competitors.
Three **personas** describe *question styles* used to author the bank — they are NOT routing
rules; every approved question is submitted to every configured target:

- **Prospect**: "what treatment is best for my symptoms? can I afford it?"
- **Provider**: "what is the diagnosis? what are the treatment options? what is the right dosing?"
- **Patient**: "is there a better option? can I afford it?"

### User Story 1 - Automated capture & storage of LLM responses (Priority: P1)

On a daily schedule, the system takes every APPROVED question, submits it to every configured
public LLM target, and stores each response as an immutable, fully-queryable record with
complete metadata and a capture status — handling provider failures without losing the run.

**Why this priority**: This is the irreducible core. Without reliable, unattended capture and
durable storage of raw responses, nothing else (scoring, alerts, dashboard) has any input. A
working run that captures and stores responses is already a usable MVP — stakeholders can read
what the LLMs said even before automated scoring exists.

**Independent Test**: Seed a small set of APPROVED questions and 3 configured targets; trigger a
run; confirm one immutable response record exists per (question × target) with full text,
metadata, and a status of SUCCESS / FAILED / TRUNCATED / BLOCKED, and that the records are
queryable by LLM, persona, therapeutic area, brand, domain, date, and status.

**Acceptance Scenarios**:

1. **Given** 100 APPROVED questions and 3 configured targets, **When** a scheduled run executes
   unattended, **Then** the run completes without manual intervention and a response record is
   stored for every question/target pair.
2. **Given** a target returns an error, **When** the system has retried up to its retry budget
   with exponential backoff and still fails, **Then** the affected record is marked FAILED, the
   run continues to the next question, and no other records are lost.
3. **Given** a response is cut off at the token limit, **When** the record is stored, **Then**
   its status is TRUNCATED and the full captured text is preserved unedited.
4. **Given** a target's safety filter blocks a response, **When** the record is stored, **Then**
   its status is BLOCKED with the block reason captured, distinct from FAILED.
5. **Given** a run is interrupted mid-execution, **When** the run is restarted, **Then** it
   resumes from the last completed question without re-submitting already-completed questions.
6. **Given** any query is dispatched or any response received, **When** the event occurs,
   **Then** an entry is written to an append-only audit log.

---

### User Story 2 - Scoring responses for sentiment, competitive position & citation status (Priority: P2)

After responses are captured, a scoring pass evaluates each one and records structured,
explainable scores as a SEPARATE versioned record linked to the response — never by altering the
response.

**Why this priority**: Scoring turns raw text into the signal stakeholders actually act on
(sentiment, competitive standing, and whether the model cited the right indication). It depends
on US1's stored responses but is independently valuable and testable against captured records.

**Independent Test**: Take a set of stored responses, run the scoring pass, and confirm each
produces a versioned scoring record containing a sentiment score in −1.0..+1.0, a competitive
position enum, a citation status, detected brands, up to five key claims, and a rationale —
without modifying the original response.

**Acceptance Scenarios**:

1. **Given** a stored response, **When** the scoring pass runs, **Then** a scoring record is
   created with `sentiment_score` (−1.0..+1.0), `competitive_position`
   (FIRST_LINE_RECOMMENDED / AMONG_OPTIONS / SECOND_LINE / NOT_RECOMMENDED / NOT_MENTIONED),
   `citation_status` (CITED / PARTIAL / ABSENT / WRONG_INDICATION), `brand_mentions`,
   `key_claims` (≤5), and `scoring_rationale`.
2. **Given** a model returns content about the wrong disease/indication, **When** scored,
   **Then** `citation_status` is WRONG_INDICATION.
3. **Given** an existing response and an updated scoring approach, **When** the response is
   re-scored, **Then** a new scoring record version is stored and the prior version is retained;
   the response record itself is unchanged.
4. **Given** a scoring record, **When** a stakeholder inspects it, **Then** the detected brands,
   key claims, and rationale are present so the score can be understood and trusted.

---

### User Story 3 - Question curation with Medical Affairs approval gate (Priority: P2)

Medical Affairs curates a versioned Question Repository and controls which questions are eligible
for submission via an approval gate: PENDING → APPROVED → REJECTED. Only APPROVED questions are
ever submitted to any LLM.

**Why this priority**: The approval gate is the compliance backbone — it prevents off-label or
promotional questions from ever reaching an external model. It is independently testable and is
the authoritative source of the content the system is otherwise agnostic to.

**Independent Test**: Add questions to the repository, exercise the approval transitions, and
confirm that a run only ever submits questions whose status is APPROVED, and that editing a
question creates a new version without deleting history.

**Acceptance Scenarios**:

1. **Given** a new question, **When** it is created, **Then** its `approval_status` defaults to
   PENDING and it is not eligible for submission.
2. **Given** a PENDING question, **When** Medical Affairs approves it, **Then** its status
   becomes APPROVED with the approver recorded, and it becomes eligible for the next run.
3. **Given** a PENDING or APPROVED question, **When** Medical Affairs rejects it, **Then** its
   status becomes REJECTED and it is excluded from all runs.
4. **Given** an APPROVED question, **When** it is edited, **Then** a new version is recorded, the
   prior version is retained, and no historical record is deleted.
5. **Given** a mix of PENDING, APPROVED, and REJECTED questions, **When** a run executes,
   **Then** only APPROVED questions are submitted.

---

### User Story 4 - Threshold-based alerts on concerning responses (Priority: P2)

The system applies deterministic threshold rules to each scoring record and raises alerts on
concerning responses, with the highest severity reserved for responses that route someone to the
wrong indication.

**Why this priority**: Alerts focus scarce stakeholder attention on the responses that matter
most. They depend on scoring (US2) but add distinct, testable value: a triaged list rather than a
raw score table.

**Independent Test**: Feed scoring records spanning the threshold boundaries and confirm that an
alert is raised exactly when a rule fires, that no alert is raised otherwise, and that a
WRONG_INDICATION citation status produces the highest-severity alert.

**Acceptance Scenarios**:

1. **Given** a scoring record with `sentiment_score` below the negative threshold, **When**
   alert rules are evaluated, **Then** an alert is raised citing the rule that fired.
2. **Given** a scoring record with `competitive_position` = NOT_RECOMMENDED, **When** evaluated,
   **Then** an alert is raised.
3. **Given** a response where a competitor brand is detected with materially higher sentiment
   than our therapy in the same response, **When** evaluated, **Then** an alert is raised.
4. **Given** a scoring record with `citation_status` = WRONG_INDICATION, **When** evaluated,
   **Then** a highest-severity alert is raised (a person routed to wrong-disease content).
5. **Given** a scoring record that breaches no threshold, **When** evaluated, **Then** no alert
   is raised.
6. **Given** identical inputs, **When** alert rules are evaluated more than once, **Then** the
   outcome is identical (decisions are deterministic and made in code, not by the model).

---

### User Story 5 - Findings dashboard, export & run summary (Priority: P3)

At the end of a run, stakeholders can review findings on a self-contained dashboard, export the
underlying records, and read a run summary — with no software to install.

**Why this priority**: The dashboard is how value is delivered to non-technical stakeholders, but
it depends on the data and signals produced by US1–US4. It is the final, independently testable
slice that makes the POC's output consumable.

**Independent Test**: With a completed scored run, open the dashboard as a single file (or shared
URL), confirm it shows sentiment distribution and competitive positioning by LLM and therapy plus
the alert list, export the records to CSV and JSON, and view the run summary.

**Acceptance Scenarios**:

1. **Given** a completed scored run, **When** a stakeholder opens the dashboard, **Then** it
   displays sentiment distribution by LLM and therapy, competitive positioning by LLM, the alert
   count with the list of flagged responses, and response volume over time — without installing
   software.
2. **Given** the dashboard, **When** a stakeholder selects a flagged response, **Then** the full
   response text is shown alongside its scoring rationale.
3. **Given** a set of query results, **When** a stakeholder exports them, **Then** CSV and JSON
   exports are produced containing the records and their scores.
4. **Given** a completed run, **When** a stakeholder views the run summary, **Then** it shows the
   run identifier, start/end time, questions attempted, responses captured by status, alert count,
   and total tokens consumed.

---

### Edge Cases

- **All targets fail for a question**: the question yields FAILED records for every target; the
  run still continues and the failures are visible in the run summary and capture-rate metric.
- **Conditional target unavailable**: Open Evidence is a single conditional target used ONLY for
  Provider-persona questions and ONLY if API access is confirmed; if unconfirmed it is deferred
  and its absence does not count against the capture rate.
- **Empty or near-empty response**: stored as captured with an appropriate status; scoring records
  ABSENT citation and a neutral/again-explained sentiment rather than failing.
- **Question edited mid-run**: the run uses the question version that was APPROVED at run start;
  later edits create a new version for the next run.
- **Re-scoring after prompt change**: produces a new versioned scoring record; historical scores
  and the original response remain intact.
- **Duplicate question content**: allowed as distinct records with distinct identifiers; curation
  surfaces duplicates for Medical Affairs but the system does not silently merge them.
- **Competitor detected but our therapy not mentioned**: handled by competitive position
  NOT_MENTIONED; the competitor-sentiment alert rule applies only when both appear in the same
  response.

## Requirements *(mandatory)*

### Functional Requirements

**Question curation & approval (US3)**

- **FR-001**: The system MUST maintain a versioned Question Repository; editing or deactivating a
  question MUST create/retain history rather than deleting records.
- **FR-002**: Each question MUST carry an `approval_status` of PENDING, APPROVED, or REJECTED,
  defaulting to PENDING, with the approver recorded on approval.
- **FR-003**: The system MUST submit ONLY questions whose status is APPROVED; PENDING and
  REJECTED questions MUST never be submitted.
- **FR-004**: Each question MUST record persona (Prospect / Provider / Patient as a *style* tag),
  therapeutic area, brand focus, and domain (Efficacy / Safety / Access / Comparative / General),
  plus an active flag.
- **FR-005**: Drug names, competitor names, and indications MUST exist ONLY in the Question
  Repository and configuration — never in application logic.

**Automated capture & storage (US1)**

- **FR-006**: The system MUST execute scheduled, unattended runs that, for each APPROVED question,
  submit to every configured target and store every response before advancing.
- **FR-007**: Every configured public LLM target (OpenAI GPT-4o, Google Gemini, Anthropic Claude
  queried as an end-user) MUST receive every approved question; Open Evidence MUST be submitted
  ONLY for Provider-persona questions and ONLY when its API access is confirmed.
- **FR-008**: Each response MUST be stored as an immutable record containing the full, unedited
  response text and complete metadata (run, question, target, timestamp, model version, persona,
  therapeutic area, brand focus, domain, token counts, finish reason).
- **FR-009**: Each response record MUST carry a status of SUCCESS, FAILED, TRUNCATED, or BLOCKED.
- **FR-010**: On target failure, the system MUST retry with exponential backoff up to a configured
  budget; after exhaustion it MUST mark the record FAILED and continue the run.
- **FR-011**: A run MUST be resumable from the last completed question without re-submitting
  already-completed questions.
- **FR-012**: The Response store MUST be queryable by any combination of LLM, persona, therapeutic
  area, brand, domain, date range, sentiment range, and alert status.
- **FR-013**: The system MUST write an append-only audit log of every query dispatched and every
  response received, sufficient for compliance review.
- **FR-014**: Adding or removing a target MUST be a configuration + adapter change only — never a
  change to core run logic; model identifiers, rate limits, and parameters MUST come from config
  and MUST never be hard-coded.

**Scoring (US2)**

- **FR-015**: The system MUST run a scoring pass that, for each stored response, produces a
  SEPARATE versioned scoring record linked to the response identifier, never mutating the response.
- **FR-016**: Each scoring record MUST include `sentiment_score` in −1.0..+1.0, `competitive_position`
  (FIRST_LINE_RECOMMENDED / AMONG_OPTIONS / SECOND_LINE / NOT_RECOMMENDED / NOT_MENTIONED),
  `citation_status` (CITED / PARTIAL / ABSENT / WRONG_INDICATION), `brand_mentions`, up to five
  `key_claims`, and a short `scoring_rationale`.
- **FR-017**: `citation_status` = WRONG_INDICATION MUST denote that the model returned content for
  the wrong disease/indication.
- **FR-018**: The system MUST support re-scoring historical responses, storing each result as a new
  scoring record version while retaining prior versions.

**Alerts (US4)**

- **FR-019**: Alert decisions MUST be made by deterministic threshold rules in code (not by the
  model) and MUST be reproducible for identical inputs.
- **FR-020**: The system MUST raise an alert when any of: `sentiment_score` is below the negative
  threshold; `competitive_position` is NOT_RECOMMENDED; a competitor brand is detected with
  materially higher sentiment than our therapy in the same response; or `citation_status` is
  WRONG_INDICATION.
- **FR-021**: A WRONG_INDICATION citation status MUST raise the highest-severity alert.
- **FR-022**: Each alert MUST record which rule fired and the reason, linked to the scoring record
  and response.

**Dashboard, export & summary (US5)**

- **FR-023**: The system MUST produce a self-contained dashboard (no software install) showing
  sentiment distribution by LLM and therapy, competitive positioning by LLM, alert count and
  flagged-response list, and response volume over time.
- **FR-024**: The dashboard MUST let a user open any flagged response to see its full text and
  scoring rationale.
- **FR-025**: The system MUST export query results to CSV and JSON.
- **FR-026**: The system MUST generate a run summary with run identifier, start/end time, questions
  attempted, responses captured by status, alert count, and total tokens consumed.

**Cross-cutting compliance**

- **FR-027**: Questions MUST be generic; no PII/PHI may be stored anywhere, and no question may be
  seeded with real patient data.
- **FR-028**: Captured responses MUST be stored only in controlled local storage and MUST NOT be
  forwarded to third parties; the system MUST comply with each target's terms of service.

### Key Entities *(include if feature involves data)*

- **Question**: a curated, versioned item approved for submission; carries persona-style tag,
  therapeutic area, brand focus, domain, active flag, approval status, approver, and version.
  One question → many responses.
- **LLM Target**: a configured public model to monitor (name, model version, parameters, rate
  limits, the personas it serves). One target → many responses.
- **Run**: a single scheduled or ad-hoc execution batch; records counts, status, tokens, cost.
  One run → many responses and audit-log entries.
- **Response**: an immutable record of one target's answer to one question in one run; full text,
  metadata, and capture status. Many responses → one question, one target, one run.
- **Scoring Record**: a versioned, derived assessment of one response (sentiment, competitive
  position, citation status, brands, key claims, rationale). Many scoring records → one response.
- **Alert**: a triggered flag linked to a scoring record and response; records the rule fired and
  reason. Many alerts → one scoring record.
- **Audit Log**: an append-only record of every external query and response for compliance.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An automated run of ~100 approved questions across 3–4 LLM targets completes with
  zero manual interventions.
- **SC-002**: The system runs unattended for 7 consecutive days with zero operator interventions.
- **SC-003**: At least 95% of submitted question/target attempts are successfully captured across
  targets (no more than 5% end FAILED after retries).
- **SC-004**: The Question Repository holds at least 30 questions per persona spanning at least 2
  therapeutic areas at POC launch.
- **SC-005**: Every captured response is stored and retrievable by each of the supported query
  dimensions (LLM, persona, therapeutic area, brand, domain, date, sentiment range, alert status).
- **SC-006**: Every scored response carries detected brands, up to five key claims, and a rationale
  (no score is presented without its supporting evidence).
- **SC-007**: Every response that meets an alert condition produces an alert, and WRONG_INDICATION
  responses are surfaced at highest severity, with no alert raised for non-breaching responses.
- **SC-008**: Medical Affairs and Commercial stakeholders confirm, at the POC readout, that the
  dashboard's baseline sentiment and competitive-positioning view is actionable.

## Assumptions

- **Approval-gate sequencing**: For the P1 capture slice, a seed set of questions may be marked
  APPROVED directly so capture can be exercised before the full curation workflow (US3) is built;
  the approval gate remains the authoritative eligibility rule.
- **Persona is a question-authoring style, not a routing rule** — every approved question goes to
  every configured target (except the Open Evidence conditional, which is Provider-only).
- **Open Evidence** is deferred unless API access is confirmed before it is needed; its absence does
  not count against the ≥95% capture target.
- **"Materially higher" competitor sentiment** uses a configurable margin (default: competitor
  sentiment exceeds our therapy's by a fixed delta) so the rule is deterministic and tunable.
- **Negative-sentiment and other alert thresholds** are configurable values, externalized from code.
- **Daily schedule** runs unattended at a configured time; ad-hoc/on-demand runs are also supported.
- **Storage and operation are local-first**; no cloud/managed services are required for the POC.
- **Stakeholders** review the dashboard at a POC readout; no per-user accounts or access control are
  required for the POC.

## Out of Scope (POC)

- Any private or internal model (only public LLMs are monitored).
- Production data-platform integrations (Veeva, Salesforce, data lake).
- Real-time notification pipelines (email / Slack / Teams push).
- Full clinical-accuracy scoring against a Medical Affairs reference library.
- User authentication, role-based access control, or multi-tenant support.
- Mobile or native applications.

## Future Capabilities *(recorded for direction only — NOT POC scope)*

The broader vision is explicitly out of POC scope and is captured here only so it is not lost:
generative-engine-optimization (GEO) analysis, a multi-agent architecture, automated
literature-mining, and pharmacovigilance signal detection. None of these are built, designed, or
committed to in this POC; they are future direction.
