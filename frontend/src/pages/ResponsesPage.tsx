import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  exportUrl,
  getDashboard,
  getResponsesTable,
  getRuns,
  type Dashboard,
  type ResponsesTable,
  type RunSummary,
} from "../api";
import Pagination from "../components/common/Pagination";
import { Segmented, Select, Td, Th } from "../components/common/Controls";
import { ResponseStatusBadge, SentimentChip } from "../components/common/StatusBadge";
import { POSITION_LABELS } from "../components/dashboard/colors";
import TargetLabel from "../components/dashboard/TargetLabel";
import ResponsePanel from "../components/reports/ResponsePanel";
import { shortDateTime } from "../lib/time";

const STATUSES = ["SUCCESS", "TRUNCATED", "BLOCKED", "FAILED"];
const tc = (s: string) => s.charAt(0) + s.slice(1).toLowerCase();

export default function ResponsesPage() {
  const [sp] = useSearchParams();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [meta, setMeta] = useState<Dashboard | null>(null);
  const [data, setData] = useState<ResponsesTable | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Filters (heatmap drill-through pre-seeds persona / llm / therapy from the query string).
  const [persona, setPersona] = useState(sp.get("persona") ?? "");
  const [therapy, setTherapy] = useState(sp.get("therapeutic_area") ?? "");
  const [status, setStatus] = useState("");
  const [period, setPeriod] = useState("all");
  const [runId, setRunId] = useState("");
  const [llms, setLlms] = useState<string[]>(sp.get("llm") ? [sp.get("llm") as string] : []);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  useEffect(() => {
    getRuns().then(setRuns).catch(() => setRuns([]));
    getDashboard({ include_dev: true }).then(setMeta).catch(() => setMeta(null));
  }, []);

  const query = useMemo(
    () => ({
      run_id: runId || undefined,
      persona: persona || undefined,
      status: status || undefined,
      therapeutic_area: therapy || undefined,
      period,
      llms,
      search: search || undefined,
      page,
      page_size: pageSize,
    }),
    [runId, persona, status, therapy, period, llms, search, page, pageSize],
  );

  useEffect(() => {
    let live = true;
    getResponsesTable(query)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [query]);

  // Any filter change resets to page 1.
  const reset = () => setPage(1);
  const toggleLlm = (id: string) => {
    reset();
    setLlms((cur) => (cur.includes(id) ? cur.filter((l) => l !== id) : [...cur, id]));
  };

  const llmOptions = meta?.options.llms ?? [];

  if (error) return <p className="mt-6 text-neg-ink">Could not load responses: {error}</p>;

  return (
    <div>
      {/* Toolbar */}
      <div className="card p-4">
        <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
          <input
            className="field min-w-[220px] flex-1"
            placeholder="Search question, model, therapy…"
            value={search}
            onChange={(e) => {
              reset();
              setSearch(e.target.value);
            }}
          />
          <Select label="Run" value={runId} onChange={(v) => { reset(); setRunId(v); }}>
            <option value="">All runs</option>
            {runs.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {r.run_id.slice(0, 8)} · {shortDateTime(r.started_at)}
              </option>
            ))}
          </Select>
          <Select label="Persona" value={persona} onChange={(v) => { reset(); setPersona(v); }}>
            <option value="">All</option>
            {(meta?.options.personas ?? ["PROSPECT", "PROVIDER", "PATIENT"]).map((p) => (
              <option key={p} value={p}>{tc(p)}</option>
            ))}
          </Select>
          <Select label="Therapy" value={therapy} onChange={(v) => { reset(); setTherapy(v); }}>
            <option value="">All</option>
            {(meta?.options.therapeutic_areas ?? []).map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </Select>
          <Select label="Status" value={status} onChange={(v) => { reset(); setStatus(v); }}>
            <option value="">All</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
          <Segmented value={period} onChange={(v) => { reset(); setPeriod(v); }} />
          <a className="btn btn-primary ml-auto" href={exportUrl(query, "csv")}>
            Export CSV
          </a>
        </div>

        {llmOptions.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-[0.7rem] font-bold uppercase tracking-wide text-ink-faint">
              LLMs {llms.length ? `(${llms.length})` : "(all)"}
            </span>
            {llmOptions.map((id) => {
              const active = llms.length === 0 || llms.includes(id);
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => toggleLlm(id)}
                  className={[
                    "rounded-full border px-3 py-1 text-xs font-semibold transition-colors",
                    active
                      ? "border-brand bg-brand-soft text-brand-dark"
                      : "border-hair bg-surface text-ink-faint hover:bg-surface-muted",
                  ].join(" ")}
                >
                  <TargetLabel name={id} />
                </button>
              );
            })}
            {llms.length > 0 && (
              <button type="button" onClick={() => { reset(); setLlms([]); }} className="text-xs text-ink-soft hover:underline">
                clear
              </button>
            )}
          </div>
        )}
      </div>

      {/* Table */}
      {!data ? (
        <p className="mt-6 text-ink-soft">Loading responses…</p>
      ) : (
        <div className="card mt-4 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hair bg-surface-muted text-left text-[0.7rem] uppercase tracking-wide text-ink-faint">
                  <Th>Captured</Th>
                  <Th>LLM</Th>
                  <Th>Persona</Th>
                  <Th>Question</Th>
                  <Th>Sentiment</Th>
                  <Th>Position</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr
                    key={r.response_id}
                    onClick={() => setOpen(r.response_id)}
                    className="cursor-pointer border-b border-hair last:border-0 hover:bg-brand-soft/40"
                  >
                    <Td className="whitespace-nowrap text-ink-soft">{shortDateTime(r.timestamp_utc)}</Td>
                    <Td><TargetLabel name={r.llm_name} /></Td>
                    <Td>{tc(r.persona)}</Td>
                    <Td>
                      <span className="font-medium text-ink">{r.question_text || r.question_id}</span>
                      <span className="mt-0.5 block text-xs text-ink-faint">
                        {r.therapeutic_area} · {tc(r.domain)}
                        {r.has_alert && <span className="ml-2 text-neg-ink">● alert</span>}
                      </span>
                    </Td>
                    <Td><SentimentChip value={r.sentiment} /></Td>
                    <Td className="text-ink-soft">
                      {r.competitive_position ? POSITION_LABELS[r.competitive_position] ?? r.competitive_position : "—"}
                    </Td>
                    <Td><ResponseStatusBadge status={r.status} /></Td>
                  </tr>
                ))}
                {data.items.length === 0 && (
                  <tr><td colSpan={7} className="p-8 text-center text-ink-soft">No responses match these filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="px-4 pb-3">
            <Pagination
              page={data.page}
              pageSize={data.page_size}
              total={data.total}
              onPage={setPage}
              onPageSize={(n) => { reset(); setPageSize(n); }}
            />
          </div>
        </div>
      )}

      {open && <ResponsePanel responseId={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
