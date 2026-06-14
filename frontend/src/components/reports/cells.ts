// Soft-tint colour map for coverage-map cells + legend. Content-agnostic: keyed by the status
// class the API already assigns (favorable/partial/negative/absent/wrong_indication/nodata).

export interface CellStyle {
  box: string; // background + text + border classes
  swatch: string; // legend swatch classes
  legend: string; // legend label
}

export const CELL_STYLES: Record<string, CellStyle> = {
  favorable: {
    box: "bg-fav-bg text-fav-ink border border-fav-ink/20",
    swatch: "bg-fav-bg border border-fav-ink/30",
    legend: "favorable",
  },
  partial: {
    box: "bg-part-bg text-part-ink border border-part-ink/20",
    swatch: "bg-part-bg border border-part-ink/30",
    legend: "partial",
  },
  negative: {
    box: "bg-neg-bg text-neg-ink border border-neg-ink/20",
    swatch: "bg-neg-bg border border-neg-ink/30",
    legend: "negative / flagged",
  },
  absent: {
    box: "bg-slate-100 text-slate-500 border border-slate-200",
    swatch: "bg-slate-100 border border-slate-300",
    legend: "absent (not mentioned)",
  },
  nodata: {
    box: "bg-surface-muted text-ink-faint border border-dashed border-slate-300",
    swatch: "bg-surface-muted border border-dashed border-slate-400",
    legend: "no answer (failed / blocked)",
  },
  wrong_indication: {
    box: "bg-wrong-bg text-wrong-ink border border-wrong-ink/20",
    swatch: "bg-wrong-bg border border-wrong-ink/30",
    legend: "wrong indication",
  },
};

export const LEGEND_ORDER = [
  "favorable",
  "partial",
  "negative",
  "absent",
  "nodata",
  "wrong_indication",
];

export function cellStyle(klass: string): CellStyle {
  return CELL_STYLES[klass] ?? CELL_STYLES.nodata;
}
