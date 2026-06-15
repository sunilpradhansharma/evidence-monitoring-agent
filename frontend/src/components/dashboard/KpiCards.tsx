import { Link } from "react-router-dom";
import type { DashKpis } from "../../api";
import { useCountUp } from "../../hooks/useCountUp";
import { timeAgo } from "../../lib/time";

function Card({
  label,
  children,
  sub,
  accent = "",
}: {
  label: string;
  children: React.ReactNode;
  sub?: React.ReactNode;
  accent?: string;
}) {
  return (
    <div className={`card lift p-4 ${accent}`}>
      <p className="text-[0.7rem] font-bold uppercase tracking-wide text-ink-faint">{label}</p>
      <div className="mt-1.5 text-[1.7rem] font-extrabold leading-none tabular-nums text-ink">
        {children}
      </div>
      {sub && <p className="mt-1.5 text-xs text-ink-soft">{sub}</p>}
    </div>
  );
}

export default function KpiCards({ kpis }: { kpis: DashKpis }) {
  const captured = useCountUp(kpis.responses_captured);
  const successPct = useCountUp(Math.round(kpis.success_rate * 100));
  const avg = useCountUp(kpis.avg_sentiment, { decimals: 2 });
  const alerts = useCountUp(kpis.active_alerts);
  const favPct = useCountUp(Math.round(kpis.favourable_pct * 100));
  const run = kpis.last_run;

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
      <Card label="Responses captured" sub={`${successPct}% success rate`}>
        {captured}
      </Card>

      <Card label="Avg sentiment" sub={`across ${kpis.scored.toLocaleString()} scored`}>
        <span className={kpis.avg_sentiment >= 0 ? "text-fav-ink" : "text-neg-ink"}>
          {kpis.avg_sentiment >= 0 ? "+" : ""}
          {avg}
        </span>
      </Card>

      <Card
        label="Active alerts"
        accent={kpis.active_alerts > 0 ? "border-l-4 border-l-neg-ink" : ""}
        sub={
          <Link to="/alerts" className="font-semibold text-brand hover:text-brand-dark">
            View alerts →
          </Link>
        }
      >
        <span className={kpis.active_alerts > 0 ? "text-neg-ink" : "text-ink"}>{alerts}</span>
      </Card>

      <Card label="Favourable positioning" sub="first-line + among-options share">
        {favPct}%
      </Card>

      <Card
        label="Last run"
        sub={
          run
            ? `${run.responses_captured.toLocaleString()} resp · ${run.questions_attempted} q · ${run.total_tokens.toLocaleString()} tok`
            : "no runs yet"
        }
      >
        <span className="text-[1.15rem]">{run ? timeAgo(run.ended_at ?? run.started_at) : "—"}</span>
      </Card>
    </div>
  );
}
