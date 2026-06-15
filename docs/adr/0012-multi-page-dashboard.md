# ADR-0012: Multi-page React dashboard (six-section nav shell) over expanded read-only `/api`

**Status:** Accepted (2026-06-14) — extends [ADR-0008](0008-react-spa-over-fastapi-readonly-api.md).

## Context

ADR-0008 introduced the React SPA as the primary UI, but as a single **Reports + Approvals**
two-route app. For the POC readout, stakeholders needed a product-shaped dashboard: a filterable
overview, a browsable response table, an alert feed, side-by-side model comparison, a question
repository view, and a run history — each a distinct workspace rather than one long Reports page.

The constraints from ADR-0008 still applied: **reuse `render.py` (no new aggregation), one app / one
URL / one command, and writes only on the existing audited approval endpoints.** The challenge was to
add several richer pages without forking the figures or adding write paths.

## Decision

- **Replace the two-tab layout with a persistent left-nav shell** of **six sections** — groups
  **INSIGHTS** (Dashboard, Responses, Alerts, LLM Comparison) and **MANAGE** (Question Repository,
  Runs) — with client-side routing. The top bar shows the current reviewer name and a **sign-out
  placeholder (no real auth — the name is only recorded on approve/reject)**, plus a run-status chip.
  The Medical Affairs **Approvals** flow (the only writes) lives as a sub-tab under Question
  Repository, unchanged and audited.
- **Add read-only `/api` endpoints that reuse `render.py`**, via the `dashboard/json_api.py`
  serializer — **no new aggregation philosophy and no new write paths**:
  - `GET /api/dashboard` — the filter-driven overview aggregate (KPIs, sentiment histogram,
    positioning shares, LLM × therapy heatmap, volume-by-week, recent alerts).
  - `GET /api/targets` — per-target `kind` + `display_name` (see ADR-0013), the frontend's single
    source of truth for labeling.
  - `GET /api/responses` — the paginated, filterable Responses table feed.
  - `GET /api/alerts` — the enriched, filterable alert feed + per-type counts.
  - `GET /api/comparison` — every target's answer + score for one (question, run).
  - Enriched `GET /api/runs` (status, tokens, cost, per-run alert count) and `GET /api/questions`
    (version-aware), alongside the ADR-0008 endpoints (`/api/runs/{id}/report`, `/api/responses/{id}`).
- **Keep behaviors consistent across surfaces** (correctness, not new features): CSV export matches
  the on-screen filtered Responses view (shared `render.filter_responses`); the Dashboard "last run"
  KPI honors the scoped run / active filters; the Dashboard "active alerts" KPI and the Alerts page
  reconcile for the same filters; the "recent alerts" header count matches the displayed list;
  heatmap drill-through carries the active filters.
- **The legacy server-rendered UI stays at `/html`** and the single-run Reports payload
  (`/api/runs/{id}/report`) is retained.

## Options considered

- **Six-section SPA over expanded read-only `/api` (chosen)** — product-shaped, still one deploy
  unit, still zero aggregation duplication, still writes only on the audited endpoints.
- **Keep the single Reports page and add more widgets to it** — simpler, but a cramped readout and no
  natural home for comparison / runs / a browsable response table.
- **Add server-side filtering/aggregation per page** — rejected; it would fork the figures and
  violate the ADR-0008 "one source of truth" goal. New endpoints serialize existing `render.py`
  results, applying only view-layer filtering (multi-target/search) the data seam doesn't express.

## Consequences

- A richer, more navigable readout with no change to capture, scoring, alert rules, orchestration,
  the data layer, or the approval write path.
- More read-only endpoints to keep in sync with the TypeScript client; each is covered by component
  tests asserting it is read-only.
- Some read paths are N+1 / load-everything (acceptable at POC size) — flagged for a
  production-hardening pass (see `docs/project-status.md`).

## Open follow-up

- A production-hardening pass for the read paths (batched score/question lookups, push pagination and
  filters into SQL).
