import type { RunSummary } from "../../api";

function label(r: RunSummary): string {
  const when = r.started_at ? r.started_at.replace("T", " ").slice(0, 16) : "—";
  return `${r.run_id.slice(0, 8)}… · ${when} · ${r.responses_captured} ok / ${r.failure_count} fail`;
}

export default function RunSelector({
  runs,
  value,
  onChange,
}: {
  runs: RunSummary[];
  value: string;
  onChange: (runId: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-[0.72rem] font-bold uppercase tracking-wide text-ink-soft">
      Run
      <select
        className="field min-w-[20rem]"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Select run"
      >
        {runs.map((r) => (
          <option key={r.run_id} value={r.run_id}>
            {label(r)}
          </option>
        ))}
      </select>
    </label>
  );
}
