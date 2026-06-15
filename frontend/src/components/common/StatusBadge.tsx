// Color-coded pills for response status and run status, using the clinical status palette.

const RESPONSE_TONE: Record<string, string> = {
  SUCCESS: "border-fav-ink/30 bg-fav-bg text-fav-ink",
  TRUNCATED: "border-part-ink/30 bg-part-bg text-part-ink",
  BLOCKED: "border-wrong-ink/30 bg-wrong-bg text-wrong-ink",
  FAILED: "border-neg-ink/30 bg-neg-bg text-neg-ink",
};

const RUN_TONE: Record<string, string> = {
  COMPLETED: "border-fav-ink/30 bg-fav-bg text-fav-ink",
  PARTIAL: "border-part-ink/30 bg-part-bg text-part-ink",
  RUNNING: "border-brand-line bg-brand-soft text-brand-dark",
};

function Pill({ label, tone }: { label: string; tone: string }) {
  return <span className={`pill ${tone || "border-hair bg-surface-muted text-ink-soft"}`}>{label}</span>;
}

export function ResponseStatusBadge({ status }: { status: string }) {
  return <Pill label={status} tone={RESPONSE_TONE[status]} />;
}

export function RunStatusBadge({ status }: { status: string }) {
  return <Pill label={status} tone={RUN_TONE[status]} />;
}

/** A signed sentiment chip (green positive, red negative); em-dash when unscored. */
export function SentimentChip({ value }: { value: number | null }) {
  if (value == null) return <span className="text-ink-faint">—</span>;
  return (
    <span className={`tabular-nums font-semibold ${value >= 0 ? "text-fav-ink" : "text-neg-ink"}`}>
      {value >= 0 ? "+" : ""}
      {value.toFixed(2)}
    </span>
  );
}
