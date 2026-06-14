import { useEffect, useState } from "react";
import { getReport, getRuns, type Report, type RunSummary } from "../../api";
import Section from "../Section";
import AlertsList from "./AlertsList";
import CitationPanel from "./CitationPanel";
import CoverageMap from "./CoverageMap";
import HowToRead from "./HowToRead";
import MetricCards from "./MetricCards";
import PositioningTable from "./PositioningTable";
import ResponsePanel from "./ResponsePanel";
import RunSelector from "./RunSelector";
import SentimentChart from "./SentimentChart";

function runLine(run: Report["run"]): string | null {
  if (!run) return null;
  const parts: string[] = [`run ${run.run_id.slice(0, 8)}`];
  if (run.started_at) parts.push(run.started_at.replace("T", " ").slice(0, 16));
  if (run.duration_seconds != null) {
    const s = Math.round(run.duration_seconds);
    parts.push(`duration ${Math.floor(s / 60)}m${s % 60}s`);
  } else {
    parts.push("in progress");
  }
  parts.push(`est. cost $${run.est_cost.toFixed(4)}`);
  parts.push(`${run.total_tokens.toLocaleString()} tokens`);
  return parts.join(" · ");
}

export default function ReportsView() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runId, setRunId] = useState<string>("");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openResponse, setOpenResponse] = useState<string | null>(null);

  useEffect(() => {
    getRuns()
      .then((rs) => {
        setRuns(rs);
        if (rs.length) setRunId(rs[0].run_id); // default to latest
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!runId) return;
    setReport(null);
    getReport(runId)
      .then(setReport)
      .catch((e) => setError(String(e)));
  }, [runId]);

  if (error) return <p className="mt-6 text-neg-ink">Could not load reports: {error}</p>;
  if (!runs.length) return <p className="mt-6 text-ink-soft">No runs yet.</p>;
  if (!report) return <p className="mt-6 text-ink-soft">Loading run…</p>;

  const line = runLine(report.run);

  return (
    <div>
      <div className="mt-2">
        <RunSelector runs={runs} value={runId} onChange={setRunId} />
      </div>

      {/* Headline band */}
      <div className="mt-4 rounded-xl border border-brand-line bg-surface border-l-4 border-l-brand p-4 shadow-card">
        <p className="text-[1.05rem] font-medium text-ink">{report.headline}</p>
      </div>

      <Section title="Run summary" note="Capture and signal counts for the selected run. The truncated and failed/blocked cards turn amber/red when a run has a problem.">
        <MetricCards m={report.metrics} gate={report.approval_gate} />
        {line && <p className="mt-2 text-xs tabular-nums text-ink-soft">{line}</p>}
      </Section>

      <Section title="Coverage map — question × model" note="How each model represented the therapy. A dashed corner tag marks a truncated response. Click a cell to read the full response and rationale.">
        <CoverageMap coverage={report.coverage} onOpen={setOpenResponse} />
      </Section>

      <Section title="Sentiment by model" note="Average sentiment toward the therapy (−1.0 to +1.0) for each model.">
        <SentimentChart rows={report.sentiment_by_model} />
      </Section>

      <Section title="Citation status" note="Whether the model cited the right indication. Wrong indication is the most serious — a person could be routed to wrong-disease content.">
        <CitationPanel counts={report.citation_counts} />
      </Section>

      <Section title="Competitive positioning by model" note="How each model ranks the therapy against alternatives, counted by bucket.">
        <PositioningTable positioning={report.positioning} />
      </Section>

      <Section title={`Alerts (${report.metrics.alert_count}) — flagged responses`} note="Each flagged response shows its question, the model, the rule that fired, and a one-line reason.">
        <AlertsList alerts={report.alerts} />
      </Section>

      <Section title="How to read this page">
        <HowToRead />
      </Section>

      {openResponse && (
        <ResponsePanel responseId={openResponse} onClose={() => setOpenResponse(null)} />
      )}
    </div>
  );
}
