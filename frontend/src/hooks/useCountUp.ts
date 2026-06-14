import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "./useReducedMotion";

interface Options {
  duration?: number;
  decimals?: number;
}

/**
 * Animate a number from 0 → target with an ease-out cubic over ~900ms on mount/value change.
 * Returns the formatted string. Honors prefers-reduced-motion (jumps straight to the value).
 */
export function useCountUp(target: number, opts: Options = {}): string {
  const { duration = 900, decimals = 0 } = opts;
  const reduced = useReducedMotion();
  const [value, setValue] = useState<number>(reduced ? target : 0);
  const frame = useRef<number>(0);

  useEffect(() => {
    if (reduced) {
      setValue(target);
      return;
    }
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(target * eased);
      if (t < 1) {
        frame.current = requestAnimationFrame(tick);
      } else {
        setValue(target);
      }
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [target, duration, reduced]);

  return decimals > 0 ? value.toFixed(decimals) : Math.round(value).toLocaleString();
}
