import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getTargets, type TargetInfo } from "../api";

// Accurate, visible tooltip keyed by target KIND (UI copy — not target identity). The "synthesis"
// note explains exactly what Synthesized Evidence is, and clarifies what it is NOT (Open Evidence).
const KIND_NOTE: Record<string, string> = {
  synthesis:
    "Synthesized Evidence synthesizes published medical literature from PubMed (E-utilities) " +
    "using Claude: it searches PubMed for the question, then writes a citation-grounded (PMID) " +
    "answer from those abstracts. It is a literature-synthesis target, provider-persona only " +
    "(so it has no answer for prospect/patient questions), and is NOT Open Evidence — it uses no " +
    "Open Evidence data and is not a commercial clinical tool.",
};

interface TargetsState {
  /** Human label for a target name (display_name from config; raw name if unknown). */
  labelFor: (name: string) => string;
  /** Config kind for a target name ("llm" | "synthesis" | "provider-api"), or undefined. */
  kindOf: (name: string) => string | undefined;
  /** Tooltip note for a target name (by kind), or undefined when there is none. */
  noteFor: (name: string) => string | undefined;
  /** The first synthesis-kind target id, if any (used to render an explicit no-response column). */
  synthesisTargetId: string | undefined;
}

const TargetsContext = createContext<TargetsState | null>(null);

export function TargetsProvider({ children }: { children: ReactNode }) {
  const [byName, setByName] = useState<Map<string, TargetInfo>>(new Map());

  useEffect(() => {
    let live = true;
    getTargets()
      .then((ts) => {
        if (live) setByName(new Map(ts.map((t) => [t.target_id, t])));
      })
      .catch(() => {
        /* labels gracefully fall back to the raw name */
      });
    return () => {
      live = false;
    };
  }, []);

  const value = useMemo<TargetsState>(() => {
    const kindOf = (name: string) => byName.get(name)?.kind;
    return {
      labelFor: (name) => byName.get(name)?.display_name ?? name,
      kindOf,
      noteFor: (name) => {
        const k = kindOf(name);
        return k ? KIND_NOTE[k] : undefined;
      },
      synthesisTargetId: [...byName.values()].find((t) => t.kind === "synthesis")?.target_id,
    };
  }, [byName]);

  return <TargetsContext.Provider value={value}>{children}</TargetsContext.Provider>;
}

export function useTargets(): TargetsState {
  const ctx = useContext(TargetsContext);
  if (!ctx) throw new Error("useTargets must be used within a TargetsProvider");
  return ctx;
}
