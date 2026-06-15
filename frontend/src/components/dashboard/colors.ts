// Chart palette derived from the clinical tokens in tailwind.config.js. Limited/dev targets get a
// muted gray so they never read as a strong LLM signal in the comparison.

const LLM_PALETTE = ["#185FA5", "#0E7C86", "#5B6BB5", "#1F8A5B", "#9B5FA8"];
const DEV_COLOR = "#8A95A3"; // ink.faint — visibly "lesser/limited"

/** Stable color for a target series. Dev/limited targets are always the muted gray. */
export function seriesColor(isFullLlm: boolean, fullIndex: number): string {
  if (!isFullLlm) return DEV_COLOR;
  return LLM_PALETTE[fullIndex % LLM_PALETTE.length];
}

// Competitive-position buckets on a favourable→unfavourable scale (green → amber → red → gray).
export const POSITION_COLORS: Record<string, string> = {
  FIRST_LINE_RECOMMENDED: "#0F6E56",
  AMONG_OPTIONS: "#4FA98C",
  SECOND_LINE: "#C9912E",
  NOT_RECOMMENDED: "#A32D2D",
  NOT_MENTIONED: "#B6BFC9",
};

export const POSITION_LABELS: Record<string, string> = {
  FIRST_LINE_RECOMMENDED: "First-line",
  AMONG_OPTIONS: "Among options",
  SECOND_LINE: "Second-line",
  NOT_RECOMMENDED: "Not recommended",
  NOT_MENTIONED: "Not mentioned",
};

// Response-status colors for the volume-over-time stack.
export const STATUS_COLORS: Record<string, string> = {
  SUCCESS: "#0F6E56",
  TRUNCATED: "#C9912E",
  BLOCKED: "#534AB7",
  FAILED: "#A32D2D",
};

export const STATUS_ORDER = ["SUCCESS", "TRUNCATED", "BLOCKED", "FAILED"];

function lerp(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t);
}

/** Diverging green-to-red scale for the heatmap: -1 red → 0 neutral → +1 green. */
export function sentimentColor(v: number): string {
  const neutral = [241, 244, 247];
  if (v >= 0) {
    const t = Math.min(1, v);
    return `rgb(${lerp(neutral[0], 15, t)}, ${lerp(neutral[1], 110, t)}, ${lerp(neutral[2], 86, t)})`;
  }
  const t = Math.min(1, -v);
  return `rgb(${lerp(neutral[0], 163, t)}, ${lerp(neutral[1], 45, t)}, ${lerp(neutral[2], 45, t)})`;
}

/** Readable text color over a heatmap cell (white on saturated cells, ink on pale ones). */
export function sentimentTextColor(v: number): string {
  return Math.abs(v) >= 0.45 ? "#FFFFFF" : "#16202B";
}
