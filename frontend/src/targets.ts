// Display labels + the how-it-works note for the optional development stand-in target.
// This target is a DEV reference only. It must ALWAYS show as "Provider evidence (dev)" — never as
// "Open Evidence" — and its output must never be attributed to Open Evidence. Open Evidence is
// referenced ONLY inside the explanatory note, as the thing this dev target stands in for.

export const PROVIDER_EVIDENCE_DEV = "provider-evidence-dev";

const DISPLAY: Record<string, string> = {
  [PROVIDER_EVIDENCE_DEV]: "Provider evidence (dev)",
};

/** Human-facing label for a target/model name (slug → display name; unknown names pass through). */
export function targetLabel(name: string): string {
  return DISPLAY[name] ?? name;
}

export function isProviderEvidenceDev(name: string): boolean {
  return name === PROVIDER_EVIDENCE_DEV;
}

/** Plain-language explanation shown wherever the dev target appears (tooltip + visible note). */
export const PROVIDER_EVIDENCE_DEV_NOTE =
  "Provider evidence (dev) — development stand-in for the Open Evidence Provider target while API " +
  "access is pending. It works in two steps: (1) it searches public PubMed literature " +
  "(E-utilities) for the question, then (2) it uses Claude to synthesize a cited answer from those " +
  "abstracts. This is NOT Open Evidence's own output and results will differ; it exists to test the " +
  "Provider pipeline. It will be replaced by the real Open Evidence API once access and Legal " +
  "sign-off are in place.";
