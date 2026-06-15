import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getRuns, type RunSummary } from "../api";
import { Td, Th } from "../components/common/Controls";
import Pagination from "../components/common/Pagination";
import { RunStatusBadge } from "../components/common/StatusBadge";
import { duration, shortDateTime } from "../lib/time";

const TRIGGER_LABEL: Record<string, string> = { ADHOC: "Ad-hoc", SCHEDULED: "Scheduled" };

function CaptureBar({ captured, failed }: { captured: number; failed: number }) {
  const total = captured + failed || 1;
  const okPct = (captured / total) * 100;
  return (
    <div className="flex items-center gap-2">
      <span className="tabular-nums">{captured.toLocaleString()}</span>
      <span className="h-2 w-20 overflow-hidden rounded-full bg-neg-bg" title={`${captured} captured · ${failed} failed`}>
        <span className="block h-full bg-fav-ink" style={{ width: `${okPct}%` }} />
      </span>
      {failed > 0 && <span className="text-xs text-neg-ink">{failed} failed</span>}
    </div>
  );
}

export default function RunsPage() {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  useEffect(() => {
    getRuns().then(setRuns).catch((e) => setError(String(e)));
  }, []);

  if (error) return <p className="mt-6 text-neg-ink">Could not load runs: {error}</p>;

  const slice = runs.slice((page - 1) * pageSize, page * pageSize);
  const copy = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard?.writeText(id);
  };

  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-hair bg-surface-muted text-left text-[0.7rem] uppercase tracking-wide text-ink-faint">
              <Th>Run</Th>
              <Th>Trigger</Th>
              <Th>Started</Th>
              <Th>Duration</Th>
              <Th>Captured</Th>
              <Th>Alerts</Th>
              <Th>Tokens</Th>
              <Th>Est. cost</Th>
              <Th>Status</Th>
            </tr>
          </thead>
          <tbody>
            {slice.map((r) => (
              <tr
                key={r.run_id}
                onClick={() => navigate(`/?run_id=${encodeURIComponent(r.run_id)}`)}
                className="cursor-pointer border-b border-hair last:border-0 hover:bg-brand-soft/40"
                title="Open this run on the Dashboard"
              >
                <Td>
                  <button onClick={(e) => copy(r.run_id, e)} className="id text-brand hover:underline" title="Copy run id">
                    {r.run_id.slice(0, 8)}
                  </button>
                </Td>
                <Td className="text-ink-soft">{TRIGGER_LABEL[r.trigger_type] ?? r.trigger_type}</Td>
                <Td className="whitespace-nowrap text-ink-soft">{shortDateTime(r.started_at)}</Td>
                <Td className="tabular-nums text-ink-soft">{duration(r.duration_seconds)}</Td>
                <Td><CaptureBar captured={r.responses_captured} failed={r.failure_count} /></Td>
                <Td className={`tabular-nums ${r.alert_count > 0 ? "font-semibold text-neg-ink" : "text-ink-soft"}`}>
                  {r.alert_count}
                </Td>
                <Td className="tabular-nums text-ink-soft">{r.total_tokens.toLocaleString()}</Td>
                <Td className="tabular-nums text-ink-soft">${r.est_cost.toFixed(4)}</Td>
                <Td><RunStatusBadge status={r.status} /></Td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr><td colSpan={9} className="p-8 text-center text-ink-soft">No runs yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="px-4 pb-3">
        <Pagination page={page} pageSize={pageSize} total={runs.length} onPage={setPage} onPageSize={(n) => { setPage(1); setPageSize(n); }} />
      </div>
    </div>
  );
}
