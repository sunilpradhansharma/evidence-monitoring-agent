import type { DashRecentAlert } from "../../api";
import { timeAgo } from "../../lib/time";
import TargetLabel from "./TargetLabel";

const TYPE_STYLE: Record<string, string> = {
  "wrong-indication": "border-wrong-ink/30 bg-wrong-bg text-wrong-ink",
  sentiment: "border-neg-ink/30 bg-neg-bg text-neg-ink",
  competitive: "border-part-ink/30 bg-part-bg text-part-ink",
};

function TypeTag({ type }: { type: string }) {
  const cls = TYPE_STYLE[type] ?? "border-hair bg-surface-muted text-ink-soft";
  return (
    <span className={`pill ${cls}`}>{type.replace("-", " ")}</span>
  );
}

export default function RecentAlerts({
  alerts,
  onOpen,
}: {
  alerts: DashRecentAlert[];
  onOpen: (responseId: string) => void;
}) {
  if (!alerts.length) {
    return <p className="text-sm text-ink-soft">No alerts for these filters.</p>;
  }
  return (
    <ul className="divide-y divide-hair">
      {alerts.map((a) => (
        <li key={a.response_id}>
          <button
            type="button"
            onClick={() => onOpen(a.response_id)}
            className="flex w-full items-center gap-3 py-3 text-left transition-colors hover:bg-surface-muted"
          >
            <TypeTag type={a.alert_type} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-ink">
                {a.question_text || a.question_id}
              </span>
              <span className="mt-0.5 flex items-center gap-2 text-xs text-ink-soft">
                <TargetLabel name={a.model} />
                <span>·</span>
                <span>{a.persona.charAt(0) + a.persona.slice(1).toLowerCase()}</span>
              </span>
            </span>
            {a.sentiment !== null && (
              <span
                className={`tabular-nums text-sm font-semibold ${a.sentiment >= 0 ? "text-fav-ink" : "text-neg-ink"}`}
              >
                {a.sentiment >= 0 ? "+" : ""}
                {a.sentiment.toFixed(2)}
              </span>
            )}
            <span className="w-16 shrink-0 text-right text-xs text-ink-faint">
              {timeAgo(a.created_at)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
