import { useGrow } from "../../hooks/useGrow";

const ORDER = ["CITED", "PARTIAL", "ABSENT", "WRONG_INDICATION"];
const LABEL: Record<string, string> = {
  CITED: "Cited",
  PARTIAL: "Partial",
  ABSENT: "Absent",
  WRONG_INDICATION: "Wrong indication",
};
const BAR: Record<string, string> = {
  CITED: "bg-fav-ink",
  PARTIAL: "bg-part-ink",
  ABSENT: "bg-slate-400",
  WRONG_INDICATION: "bg-wrong-ink",
};

function Row({ status, count, max }: { status: string; count: number; max: number }) {
  const targetPct = max > 0 ? (count / max) * 100 : 0;
  const width = useGrow(targetPct);
  const isWrong = status === "WRONG_INDICATION";
  return (
    <div className="flex items-center gap-3 py-1.5">
      <div
        className={`w-32 shrink-0 text-sm font-semibold ${isWrong ? "text-wrong-ink" : "text-ink"}`}
        title={
          isWrong ? "The model returned content for the wrong disease/indication." : undefined
        }
      >
        {LABEL[status]}
      </div>
      <div className="h-3 flex-1 overflow-hidden rounded bg-surface-muted">
        <div
          className={`h-full rounded ${BAR[status]} transition-[width] duration-700 ease-out`}
          style={{ width: `${width}%` }}
        />
      </div>
      <div className="w-8 text-right text-sm font-bold tabular-nums">{count}</div>
    </div>
  );
}

export default function CitationPanel({ counts }: { counts: Record<string, number> }) {
  const max = Math.max(1, ...ORDER.map((s) => counts[s] ?? 0));
  return (
    <div className="card p-4">
      {ORDER.map((s) => (
        <Row key={s} status={s} count={counts[s] ?? 0} max={max} />
      ))}
    </div>
  );
}
