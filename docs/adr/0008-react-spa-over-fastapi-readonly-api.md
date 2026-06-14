# ADR-0008: React SPA as the primary UI, served by FastAPI over a read-only `/api` layer

**Status:** Accepted (2026-06-14)

## Context

ADR-0005 shipped a single local FastAPI app with a server-rendered (Jinja) **Reports + Approvals**
UI. That UI proved the workflow, but for the POC readout we wanted a more dynamic, presentation-
quality dashboard (animated metric cards, a question × model coverage heatmap, a charted sentiment
view, a click-through response panel) without changing any capture, scoring, alert, orchestration,
data-layer, or approval logic.

Two constraints shaped the decision:

- **No new aggregation.** The server-rendered Reports view already computes everything
  (`dashboard/render.py`: `build_report`, run metrics, coverage rows/cells, citation counts,
  alerts-by-type, sentiment-by-model, positioning, the approval gate, version-aware counts). A new
  UI must **reuse** that, not re-derive it.
- **One app, one URL, one command.** The system stays local-first and dependency-light to run; no
  separate frontend server should be required to *use* it.

## Decision

- **Build the primary UI as a React + TypeScript single-page app** (Vite, Tailwind, Inter via
  `@fontsource/inter`, Recharts for the sentiment chart) under `frontend/`. It builds to static
  files in `frontend/dist/`.
- **FastAPI serves the built SPA at `/`** (`api.py` → `_register_spa`): it mounts the hashed assets
  at `/assets` and serves `index.html` for `/` and for unknown client-side routes (SPA fallback),
  registered **last** so it never shadows an explicit API/HTML route. When no build is present
  (fresh checkout / CI), `/` falls back to the legacy server-rendered HTML, so the backend never
  hard-depends on a frontend build.
- **Add read-only JSON endpoints under `/api`** that serialize what `render.py` already computes,
  via a thin serializer module (`dashboard/json_api.py`) — **no new aggregation logic**:
  - `GET /api/runs` — runs for the run selector.
  - `GET /api/runs/{run_id}/report` — the full Reports payload for one run (`build_report`).
  - `GET /api/questions?status=&persona=` — version-aware questions + global status counts.
  - `GET /api/responses/{response_id}` — full response text + scoring rationale (click-through).
- **Writes are unchanged.** Approve / reject / edit still go through the existing audited
  `POST /approvals/questions/{id}/...` endpoints; the SPA calls them directly. No new write path
  exists.
- **The legacy server-rendered UI is kept, moved to `/html`.** It shares the same read-only render
  path and the same approval endpoints, so it remains a working fallback during the transition.

## Options considered

- **React SPA + read-only `/api` reusing `render.py` (chosen)** — dynamic UI, single deploy unit,
  zero duplication of aggregation, writes still on the audited endpoints.
- **Keep server-rendered Jinja only** — simplest, but limited interactivity for the readout.
- **Separate frontend dev server in production** — two processes / two URLs; rejected as it breaks
  the single-command local-first model (a Vite dev server is used for development only, proxying
  `/api` and `/approvals` to the backend).
- **New aggregation in the API layer** — rejected; it would fork the figures shown by the HTML and
  the JSON and violate the "one source of truth" goal.

## Consequences

- The dashboard is now a build artifact: production is `npm run build` then
  `uv run uvicorn evidence_monitor.api:app`. The Python test suite stays build-independent (it
  targets `/api/*` and the legacy `/html`), so it passes with or without `frontend/dist/`.
- `frontend/node_modules` and `frontend/dist` are git-ignored; the build is reproducible from
  `package.json`.
- The `/api` endpoints are strictly read-only and asserted as such by `tests/component/test_json_api.py`.
- This **supersedes the UI-rendering portion of ADR-0005**; ADR-0005's other decisions (single
  local-only app, `approver_name` attribution, no RBAC, the only outward action is changing approval
  status) remain in force.
