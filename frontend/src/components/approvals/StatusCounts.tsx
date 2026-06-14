import type { QuestionsPayload } from "../../api";

function Stat({ n, label }: { n: number; label: string }) {
  return (
    <span className="rounded-lg border border-hair bg-surface px-4 py-2 text-sm font-semibold text-ink-soft shadow-card">
      <b className="mr-1 text-xl font-extrabold tabular-nums text-ink">{n}</b>
      {label}
    </span>
  );
}

export default function StatusCounts({ counts }: { counts: QuestionsPayload["counts"] }) {
  return (
    <div className="mt-3 flex flex-wrap gap-2.5">
      <Stat n={counts.pending} label="Pending" />
      <Stat n={counts.approved} label="Approved" />
      <Stat n={counts.rejected} label="Rejected" />
      <Stat n={counts.total} label="Total questions" />
    </div>
  );
}
