import type { ReactNode } from "react";
import type { ApprovalGate, Metrics } from "../../api";
import { useCountUp } from "../../hooks/useCountUp";

type Tone = "neutral" | "good" | "warn" | "bad";

const TONE: Record<Tone, { card: string; bar: string; value: string }> = {
  neutral: { card: "bg-surface border-hair", bar: "bg-slate-300", value: "text-ink" },
  good: { card: "bg-fav-bg border-fav-ink/20", bar: "bg-fav-ink", value: "text-fav-ink" },
  warn: { card: "bg-part-bg border-part-ink/20", bar: "bg-part-ink", value: "text-part-ink" },
  bad: { card: "bg-neg-bg border-neg-ink/20", bar: "bg-neg-ink", value: "text-neg-ink" },
};

function MetricCard({
  label,
  value,
  decimals = 0,
  suffix,
  extra,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: number;
  decimals?: number;
  suffix?: string;
  extra?: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
}) {
  const shown = useCountUp(value, { decimals });
  const t = TONE[tone];
  return (
    <div className={`lift relative overflow-hidden rounded-xl border p-5 shadow-card ${t.card}`}>
      <span className={`absolute inset-y-0 left-0 w-1 ${t.bar}`} aria-hidden="true" />
      <div className="text-[0.72rem] font-bold uppercase tracking-wider text-ink-soft">{label}</div>
      <div className={`mt-2 text-3xl font-extrabold tabular-nums ${t.value}`}>
        {shown}
        {suffix}
        {extra}
      </div>
      {sub && <div className="mt-2 text-xs text-ink-soft">{sub}</div>}
    </div>
  );
}

export default function MetricCards({ m, gate }: { m: Metrics; gate: ApprovalGate }) {
  const byType = Object.entries(m.alerts_by_type);
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      <MetricCard label="Responses" value={m.total} sub="total in view" />
      <MetricCard
        label="Success"
        value={m.success}
        sub="complete answers"
        tone={m.success > 0 && m.failed_blocked === 0 ? "good" : "neutral"}
      />
      <MetricCard
        label="Truncated"
        value={m.truncated}
        tone={m.truncated > 0 ? "warn" : "good"}
        sub={m.truncated > 0 ? "cut off — partial text kept" : "none cut off"}
      />
      <MetricCard
        label="Failed / blocked"
        value={m.failed_blocked}
        tone={m.failed_blocked > 0 ? "bad" : "good"}
        sub={`${m.failed} failed · ${m.blocked} blocked`}
      />
      <MetricCard
        label="Capture rate"
        value={m.capture_rate_pct}
        suffix="%"
        tone={m.total === 0 ? "neutral" : m.capture_ok ? "good" : "bad"}
        extra={
          m.total > 0 ? (
            <span className="ml-1 text-xl">{m.capture_ok ? "✓" : "✗"}</span>
          ) : null
        }
        sub={`target ≥ ${Math.round(m.capture_target_pct)}%`}
      />
      <MetricCard
        label="Alerts"
        value={m.alert_count}
        tone={m.alert_count > 0 ? "warn" : "neutral"}
        sub={
          byType.length
            ? byType.map(([t, n]) => `${t} ${n}`).join(" · ")
            : "none"
        }
      />
      <MetricCard
        label="Scope"
        value={m.question_count}
        suffix={` × ${m.model_count}`}
        sub="questions × models"
      />
      <MetricCard
        label="Approval gate"
        value={gate.approved}
        suffix={` / ${gate.pending}`}
        sub="approved / pending"
      />
    </div>
  );
}
