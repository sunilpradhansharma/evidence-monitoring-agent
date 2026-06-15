import { useEffect, useMemo, useState } from "react";
import {
  getAlertsFeed,
  getDashboard,
  type AlertsFeed,
  type Dashboard,
} from "../api";
import { Segmented, Select, Td, Th } from "../components/common/Controls";
import Pagination from "../components/common/Pagination";
import { SentimentChip } from "../components/common/StatusBadge";
import TargetLabel from "../components/dashboard/TargetLabel";
import ResponsePanel from "../components/reports/ResponsePanel";
import { timeAgo } from "../lib/time";

// Friendly labels for the REAL engine rule types (no invented types).
const RULE_LABEL: Record<string, string> = {
  NEGATIVE_SENTIMENT: "Negative sentiment",
  NOT_RECOMMENDED: "Not recommended",
  COMPETITOR_HIGHER: "Competitor higher",
  WRONG_INDICATION: "Wrong indication",
};
const RULE_ORDER = ["WRONG_INDICATION", "NOT_RECOMMENDED", "COMPETITOR_HIGHER", "NEGATIVE_SENTIMENT"];
const TYPE_STYLE: Record<string, string> = {
  "wrong-indication": "border-wrong-ink/30 bg-wrong-bg text-wrong-ink",
  sentiment: "border-neg-ink/30 bg-neg-bg text-neg-ink",
  competitive: "border-part-ink/30 bg-part-bg text-part-ink",
};
const SEV_LABEL: Record<number, string> = { 1: "Low", 2: "Medium", 3: "High" };
const SEV_STYLE: Record<number, string> = {
  3: "border-neg-ink/30 bg-neg-bg text-neg-ink",
  2: "border-part-ink/30 bg-part-bg text-part-ink",
  1: "border-brand-line bg-brand-soft text-brand-dark",
};
const tc = (s: string) => s.charAt(0) + s.slice(1).toLowerCase();

export default function AlertsPage() {
  const [meta, setMeta] = useState<Dashboard | null>(null);
  const [data, setData] = useState<AlertsFeed | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [rule, setRule] = useState("");
  const [persona, setPersona] = useState("");
  const [llm, setLlm] = useState("");
  const [severity, setSeverity] = useState("");
  const [period, setPeriod] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  useEffect(() => {
    getDashboard({ include_dev: true }).then(setMeta).catch(() => setMeta(null));
  }, []);

  const query = useMemo(
    () => ({
      rule: rule || undefined,
      persona: persona || undefined,
      llm: llm || undefined,
      severity: severity ? Number(severity) : undefined,
      period,
      page,
      page_size: pageSize,
    }),
    [rule, persona, llm, severity, period, page, pageSize],
  );

  useEffect(() => {
    let live = true;
    getAlertsFeed(query)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [query]);

  const reset = () => setPage(1);
  if (error) return <p className="mt-6 text-neg-ink">Could not load alerts: {error}</p>;

  // KPI tiles: total + one per REAL rule type present in the data (data-driven; nothing invented).
  const counts = data?.counts_by_rule ?? {};
  const presentRules = RULE_ORDER.filter((r) => counts[r] != null);
  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <div>
      {/* KPI tiles */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Tile label="Total alerts" value={total} accent="border-l-4 border-l-neg-ink" />
        {presentRules.map((r) => (
          <Tile key={r} label={RULE_LABEL[r] ?? r} value={counts[r]} />
        ))}
      </div>

      {/* Filters */}
      <div className="card mt-4 p-4">
        <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
          <Select label="Alert type" value={rule} onChange={(v) => { reset(); setRule(v); }}>
            <option value="">All types</option>
            {presentRules.map((r) => <option key={r} value={r}>{RULE_LABEL[r] ?? r}</option>)}
          </Select>
          <Select label="LLM" value={llm} onChange={(v) => { reset(); setLlm(v); }}>
            <option value="">All</option>
            {(meta?.options.llms ?? []).map((l) => <option key={l} value={l}>{l}</option>)}
          </Select>
          <Select label="Persona" value={persona} onChange={(v) => { reset(); setPersona(v); }}>
            <option value="">All</option>
            {(meta?.options.personas ?? ["PROSPECT", "PROVIDER", "PATIENT"]).map((p) => (
              <option key={p} value={p}>{tc(p)}</option>
            ))}
          </Select>
          <Select label="Severity" value={severity} onChange={(v) => { reset(); setSeverity(v); }}>
            <option value="">All</option>
            <option value="3">High</option>
            <option value="2">Medium</option>
            <option value="1">Low</option>
          </Select>
          <Segmented value={period} onChange={(v) => { reset(); setPeriod(v); }} />
        </div>
      </div>

      {/* Feed */}
      {!data ? (
        <p className="mt-6 text-ink-soft">Loading alerts…</p>
      ) : (
        <div className="card mt-4 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hair bg-surface-muted text-left text-[0.7rem] uppercase tracking-wide text-ink-faint">
                  <Th>Severity</Th>
                  <Th>Type</Th>
                  <Th>LLM</Th>
                  <Th>Persona</Th>
                  <Th>Therapy</Th>
                  <Th>Question</Th>
                  <Th>Sentiment</Th>
                  <Th>Time</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((a) => (
                  <tr
                    key={a.alert_id}
                    onClick={() => setOpen(a.response_id)}
                    className="cursor-pointer border-b border-hair last:border-0 hover:bg-brand-soft/40"
                  >
                    <Td><span className={`pill ${SEV_STYLE[a.severity] ?? ""}`}>{SEV_LABEL[a.severity] ?? a.severity}</span></Td>
                    <Td><span className={`pill ${TYPE_STYLE[a.alert_type] ?? "border-hair bg-surface-muted text-ink-soft"}`}>{a.alert_type.replace("-", " ")}</span></Td>
                    <Td><TargetLabel name={a.model} /></Td>
                    <Td>{tc(a.persona)}</Td>
                    <Td className="text-ink-soft">{a.therapeutic_area}</Td>
                    <Td><span className="font-medium text-ink">{a.question_text || a.question_id}</span></Td>
                    <Td><SentimentChip value={a.sentiment} /></Td>
                    <Td className="whitespace-nowrap text-ink-faint">{timeAgo(a.created_at)}</Td>
                  </tr>
                ))}
                {data.items.length === 0 && (
                  <tr><td colSpan={8} className="p-8 text-center text-ink-soft">No alerts match these filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="px-4 pb-3">
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} onPageSize={(n) => { reset(); setPageSize(n); }} />
          </div>
        </div>
      )}

      {open && <ResponsePanel responseId={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function Tile({ label, value, accent = "" }: { label: string; value: number; accent?: string }) {
  return (
    <div className={`card lift p-4 ${accent}`}>
      <p className="text-[0.7rem] font-bold uppercase tracking-wide text-ink-faint">{label}</p>
      <p className="mt-1.5 text-[1.7rem] font-extrabold leading-none tabular-nums text-ink">
        {value.toLocaleString()}
      </p>
    </div>
  );
}
