import type { AlertItem } from "../../api";

const SEV_BADGE: Record<number, string> = {
  3: "bg-wrong-bg text-wrong-ink border-wrong-ink/30",
  2: "bg-neg-bg text-neg-ink border-neg-ink/30",
  1: "bg-part-bg text-part-ink border-part-ink/30",
};
const SEV_BAR: Record<number, string> = {
  3: "border-l-wrong-ink",
  2: "border-l-neg-ink",
  1: "border-l-part-ink",
};

export default function AlertsList({ alerts }: { alerts: AlertItem[] }) {
  if (!alerts.length) return <p className="italic text-ink-soft">No alerts in view.</p>;
  return (
    <div className="space-y-3">
      {alerts.map((a) => (
        <div
          key={a.response_id}
          className={`card border-l-4 p-4 ${SEV_BAR[a.severity] ?? "border-l-slate-400"}`}
        >
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded border px-2 py-0.5 text-[0.7rem] font-extrabold uppercase tracking-wide ${
                SEV_BADGE[a.severity] ?? "bg-slate-100 text-slate-600 border-slate-300"
              }`}
            >
              sev {a.severity}
            </span>
            <span className="font-extrabold">{a.question_id}</span>
            <span className="tag tag-muted">{a.model}</span>
            <span className="tag tag-muted">{a.persona.toLowerCase()}</span>
            {a.rules.map((r, i) => (
              <span key={i} className="pill border-brand-line bg-brand-soft text-brand-dark">
                {r.rule}
              </span>
            ))}
            {a.truncated && (
              <span className="pill border-part-ink/30 bg-part-bg text-part-ink">truncated / partial</span>
            )}
          </div>
          {a.question_text && (
            <p className="mt-2 text-sm leading-relaxed text-ink">
              <span className="font-semibold">Q:</span> {a.question_text}
            </p>
          )}
          <ul className="mt-1.5 list-disc pl-5 text-sm text-ink-soft">
            {a.rules.map((r, i) => (
              <li key={i}>
                <span className="font-semibold">{r.rule}:</span> {r.reason}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
