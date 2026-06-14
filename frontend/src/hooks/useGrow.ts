import { useEffect, useState } from "react";
import { useReducedMotion } from "./useReducedMotion";

/**
 * Returns a width percentage that grows from 0 → target on mount (for animated bars).
 * With reduced motion it returns the target immediately.
 */
export function useGrow(targetPct: number, delay = 60): number {
  const reduced = useReducedMotion();
  const [pct, setPct] = useState<number>(reduced ? targetPct : 0);
  useEffect(() => {
    if (reduced) {
      setPct(targetPct);
      return;
    }
    const id = window.setTimeout(() => setPct(targetPct), delay);
    return () => window.clearTimeout(id);
  }, [targetPct, delay, reduced]);
  return pct;
}
