# ADR-0014: "Synthesized Evidence" — a first-class literature-synthesis target (PubMed + Claude)

**Status:** Accepted (2026-06-14) — supersedes [ADR-0011](0011-provider-evidence-dev-target.md).

## Context

ADR-0011 introduced a PubMed+Claude Provider target (id `provider-evidence-dev`) framed as a
"development stand-in" for the future Open Evidence Provider integration, displayed as "Provider
evidence (dev)" and treated as a secondary/limited target. Two problems emerged:

- **Framing.** Describing the target only as a "stand-in for Open Evidence" defines it by a
  third-party product it is not, and the "(dev)" label undersold a genuinely useful capability: an
  evidence-grounded answer synthesized from public, published literature.
- **Classification.** Treating it as a limited/dev target (and excluding it from the default view)
  relied on the persona-count heuristic that ADR-0013 replaces.

The target's **mechanism is sound and worth keeping**: it grounds a Provider-persona answer in public
PubMed literature with PMID citations, and exercises the Provider pipeline end-to-end.

## Decision

- **Rename the target's display name to "Synthesized Evidence"** everywhere it surfaces (dashboard,
  responses, alerts, comparison, CLI, and the response provenance footer). The internal id /
  `llm_name` stay `provider-evidence-dev` so stored provenance and the adapter registry are stable.
- **Name it for what it does, not for what it is not.** It is a **literature-synthesis** target:
  it queries public **PubMed E-utilities** (`esearch` → `efetch`) for the question, then uses the
  Claude client (orchestrator role) to write a concise, **PMID-cited** answer **from the retrieved
  abstracts only**. It is **not attributed to any third-party product and uses no Open Evidence
  data**; "Open Evidence" appears only in an explanatory note clarifying what it is *not*.
- **Classify it `kind: synthesis`** (ADR-0013) and treat it as **first-class** — shown in the
  dashboard alongside the LLMs by default, with no "dev" badge (an informational tooltip explains the
  PubMed + Claude method). It remains **Provider-persona only**, so it has no answer for
  prospect/patient questions; those render as "n/a"/no-response, never a misleading score.
- **Provenance unchanged** — the PubMed query + the PMIDs used are recorded in the immutable response
  text (a delimited Sources footer); a PubMed outage is retried then marked `FAILED` so the run
  continues (Principle IX). No data-layer or Response-schema change.
- **Open Evidence stays distinct and out of scope here** — the real `open-evidence` target
  (`kind: provider-api`, `active: false`) remains a separate future task; Synthesized Evidence is not
  a placeholder *for it* in the UI's framing, it is its own target.

## Options considered

- **Rename to "Synthesized Evidence", first-class, `kind: synthesis` (chosen)** — honest (named for
  its method), correctly classified by config, and presented as the real capability it is.
- **Keep the "Provider evidence (dev)" stand-in framing (ADR-0011)** — superseded; it defined the
  target by a product it is not and under-represented a working capability.
- **Attribute synthesized answers to a third-party product** — rejected outright (and unchanged from
  ADR-0011): dishonest attribution / fabricated provenance.

## Consequences

- A first-class, honestly-named Provider target whose label describes its actual method; no user can
  read it as a commercial clinical tool, and it is never attributed to Open Evidence (asserted by
  tests that its surfaced names never contain "Open Evidence").
- The mechanism, provenance, retry/backoff, and offline-mock behavior are unchanged from ADR-0011.
- A small external dependency on NCBI E-utilities remains, behind the adapter and adding no required
  credential beyond `ANTHROPIC_API_KEY` (optional NCBI email/api_key for higher rate limits).

## Open follow-up

- The real Open Evidence Provider API integration (`kind: provider-api`) remains a separate future
  task (API key + org id + signed BAA + Legal/ToS sign-off); it slots into the same adapter seam.
