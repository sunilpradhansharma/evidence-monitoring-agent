# ADR-0011: A labeled PubMed+Claude "Provider evidence (dev)" stand-in — explicitly NOT Open Evidence

**Status:** Superseded by [ADR-0014](0014-synthesized-evidence-target.md) (2026-06-14).

> **Superseded.** The same PubMed+Claude target (id `provider-evidence-dev`) was **renamed to
> "Synthesized Evidence"** and reframed as a **first-class literature-synthesis target** (config
> `kind: synthesis`) rather than a "dev stand-in"; it is named for what it does and is not framed in
> relation to any third-party product. The mechanism (PubMed E-utilities + Claude synthesis,
> Provider-persona only, PMID provenance, graceful failure) is unchanged. See ADR-0014 for the
> current decision; the context below is retained for history.

## Context

The Provider-persona pipeline needs an evidence-grounded Provider target to exercise end-to-end,
but the real **Open Evidence** Provider integration is not yet available: it requires an API key +
organization id + a signed BAA obtained through Open Evidence's sales process, plus Legal/ToS
sign-off (ADR-0006 / FR-007). Until that lands, the Provider column of the dashboard would be empty,
and the Provider pipeline (gating, capture, scoring, alerts, provenance) would go unexercised.

A naïve shortcut — labeling *any* synthesized answer as "Open Evidence" — would be dishonest and
dangerous: it would fabricate competitive intelligence and could mislead Medical Affairs into
treating a stand-in's output as Open Evidence's actual answer.

## Decision

Add an **optional development stand-in** target, id `provider-evidence-dev`, display name
**"Provider evidence (dev)"**, Provider-persona only, behind the existing `llm` adapter seam (a new
adapter class + a `targets.yaml` entry — no core/orchestration change, Principle V/X). It works in
two steps:

1. **Retrieve** — query public **PubMed E-utilities** (`esearch` → `efetch`) for the question text
   to get a small set of recent abstracts. NCBI identification (`tool` + `email`) comes from config;
   an optional `api_key` (config/env, held as `SecretStr`) raises rate limits. Basic access needs no
   key, so it adds no *required* credential.
2. **Synthesize** — pass those abstracts to the existing Claude client (orchestrator role) and ask
   it to write a concise, citation-grounded answer **from the provided abstracts only** (the prompt
   states these are abstracts, not full text). The synthesized text + a provenance footer (the
   PubMed query and the PMIDs used) becomes the captured response, scored through the normal pipeline.

**Honest attribution is the core constraint:** this target is **NEVER** presented as, or attributed
to, Open Evidence. The id, `llm_name`, display name, CLI output, and every UI surface read "Provider
evidence (dev)"; the string "Open Evidence" appears **only** inside an explanatory how-it-works note
(tooltip in the coverage-map column header + a visible caption + a note in the response-detail view)
that states it is a stand-in, that results differ from Open Evidence's, and that it will be replaced
by the real Open Evidence API.

Provenance is stored in the **immutable response text** (a delimited Sources footer with the query +
PMIDs), preserving traceability without changing the data layer or the Response schema. PubMed
failures are transient-retried and then marked `FAILED` so the run continues (Principle IX).

The committed config currently has it `active: true` so the Provider pipeline is exercised in
readouts; it can be disabled with a single `active: false` flip. Open Evidence itself stays
`active: false`.

## Options considered

- **Labeled PubMed+Claude dev stand-in (chosen)** — exercises the Provider pipeline now, honestly
  labeled, reuses the adapter seam and the Claude client; trivially swapped for the real adapter.
- **Leave the Provider column empty until Open Evidence is live** — honest but leaves the Provider
  pipeline untested and the dashboard Provider view blank through the readout.
- **Reuse a general LLM and label it "Open Evidence"** — rejected outright: dishonest attribution and
  fabricated competitive intelligence.
- **Store provenance as new DB columns** — rejected for the POC: it would change the data layer; the
  immutable-response-text footer gives traceability without that change.

## Consequences

- The Provider-persona pipeline is fully exercised (capture → score → alert → provenance) before the
  real integration exists.
- A clear, enforced naming boundary: the stand-in can never be mistaken for Open Evidence (asserted
  by a unit test that the target's name is never the literal "Open Evidence").
- A small new external dependency (NCBI E-utilities) behind the adapter, guarded by retry/backoff and
  graceful failure; it adds no required credential.
- The real Open Evidence adapter remains a pending future task; it slots into the same seam (new
  adapter + config), and this stand-in is removed or set inactive when it lands.
