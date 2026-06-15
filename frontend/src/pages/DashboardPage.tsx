import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { getDashboard, type Dashboard } from "../api";
import Section from "../components/Section";
import FilterBar, { type DashFilterState } from "../components/dashboard/FilterBar";
import KpiCards from "../components/dashboard/KpiCards";
import PositioningBars from "../components/dashboard/PositioningBars";
import RecentAlerts from "../components/dashboard/RecentAlerts";
import SentimentHeatmap from "../components/dashboard/SentimentHeatmap";
import SentimentHistogram from "../components/dashboard/SentimentHistogram";
import VolumeChart from "../components/dashboard/VolumeChart";
import ResponsePanel from "../components/reports/ResponsePanel";

const INITIAL: DashFilterState = {
  persona: "",
  therapeutic_area: "",
  period: "all",
  llms: [],
};

export default function DashboardPage() {
  const navigate = useNavigate();
  const [sp, setSp] = useSearchParams();
  const runId = sp.get("run_id") ?? undefined;
  const [filters, setFilters] = useState<DashFilterState>(INITIAL);
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openResponse, setOpenResponse] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getDashboard({ ...filters, run_id: runId })
      .then((d) => live && setData(d))
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [filters, runId]);

  if (error) return <p className="mt-6 text-neg-ink">Could not load dashboard: {error}</p>;

  const drillToResponses = (targetId: string, therapeuticArea: string) => {
    const p = new URLSearchParams();
    if (filters.persona) p.set("persona", filters.persona);
    p.set("llm", targetId);
    p.set("therapeutic_area", therapeuticArea);
    navigate(`/responses?${p.toString()}`);
  };

  return (
    <div>
      {runId && (
        <div className="mb-3 flex items-center justify-between rounded-lg border border-brand-line bg-brand-soft px-4 py-2 text-sm">
          <span className="text-brand-dark">
            Scoped to run <span className="id font-semibold">{runId.slice(0, 8)}</span>
          </span>
          <button
            type="button"
            className="font-semibold text-brand hover:text-brand-dark"
            onClick={() => setSp({}, { replace: true })}
          >
            Clear ✕
          </button>
        </div>
      )}
      <FilterBar
        options={data?.options ?? { personas: [], therapeutic_areas: [], llms: [] }}
        targets={data?.targets ?? []}
        value={filters}
        onChange={setFilters}
      />

      {!data ? (
        <p className="mt-6 text-ink-soft">Loading dashboard…</p>
      ) : (
        <>
          <div className="mt-5">
            <KpiCards kpis={data.kpis} />
          </div>

          <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
            <Section
              title="Sentiment distribution by LLM"
              note="How sentiment toward the therapy spreads across the −1…+1 scale, one series per model."
              className="!mt-0"
            >
              <SentimentHistogram histogram={data.sentiment_histogram} />
            </Section>

            <Section
              title="Competitive positioning by LLM"
              note="Share of each position bucket per model (first-line → not-mentioned)."
              className="!mt-0"
            >
              <PositioningBars positioning={data.positioning} />
            </Section>

            <Section
              title="Sentiment by LLM × therapy area"
              note="Mean sentiment per cell; green is favourable, red is negative. Click a cell to drill into its responses. Empty cells are n/a."
              className="!mt-0"
            >
              <SentimentHeatmap heatmap={data.heatmap} onCell={drillToResponses} />
            </Section>

            <Section
              title="Volume over time"
              note="Responses captured per week, stacked by status."
              className="!mt-0"
            >
              <VolumeChart weeks={data.volume_by_week} />
            </Section>
          </div>

          <Section
            title={`Recent alerts (${data.kpis.active_alerts})`}
            note="Latest flagged responses. Click one to read the full response and rationale."
          >
            <RecentAlerts alerts={data.recent_alerts} onOpen={setOpenResponse} />
          </Section>
        </>
      )}

      {openResponse && (
        <ResponsePanel responseId={openResponse} onClose={() => setOpenResponse(null)} />
      )}
    </div>
  );
}
