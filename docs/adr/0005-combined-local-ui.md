# ADR-0005: Combined Reports + Approvals UI, local-only, approver-name, no RBAC

**Status:** Accepted (2026-06-13). **UI-rendering portion superseded by
[ADR-0008](0008-react-spa-over-fastapi-readonly-api.md)** — the primary UI is now a React SPA served
by FastAPI over read-only `/api` endpoints, and the original server-rendered (Jinja) UI is retained
at `/html`. The decisions below that remain **in force**: a single local-only app, `approver_name`
attribution, no RBAC, and that the only outward action the app can take is changing a question's
approval status (it never submits a question to an LLM).

## Context

The POC needs two interfaces: a way for Medical Affairs to approve questions, and a way for
stakeholders to review findings. Full authentication, role-based access control, and multi-tenant
support are explicitly out of POC scope, but approvals must still be attributable.

## Decision

Ship **one FastAPI app** (`api.py`) serving both:

- **Reports** — **read-only** endpoints for responses, drill-down, exports, alerts, and run
  summaries.
- **Approvals** — **read-write** endpoints for Medical Affairs to approve/reject/edit questions.

The app is **local-only** (no public exposure, no auth). Approvals record an **`approver_name`**
for attribution. **No RBAC / multi-tenant** in the POC. The only outward-affecting action the app
can take is changing a question's approval status — it can never submit a question to an LLM
(submission happens only inside scheduled/CLI runs over APPROVED questions).

## Options considered

- **Combined local app, approver-name, no RBAC (chosen)** — minimal, attributable, fits POC scope.
- **Separate Reports and Approvals apps** — cleaner separation but more to build/run for no POC benefit.
- **Full auth + RBAC now** — explicitly out of scope; large effort, not needed for a local POC.

## Consequences

- Attribution without the cost of an identity system.
- Must not be exposed beyond localhost; production will need real authn/authz (deferred).

## Open follow-up

- Define the production authentication/RBAC model before any non-local deployment.
