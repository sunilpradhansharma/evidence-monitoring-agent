import { useEffect, useMemo, useState } from "react";
import {
  getComparison,
  getQuestions,
  getRuns,
  type Comparison,
  type ComparisonColumn,
  type QuestionItem,
  type RunSummary,
} from "../api";
import { Select } from "../components/common/Controls";
import { SentimentChip } from "../components/common/StatusBadge";
import { POSITION_LABELS } from "../components/dashboard/colors";
import TargetLabel from "../components/dashboard/TargetLabel";
import { PROVIDER_EVIDENCE_DEV, isProviderEvidenceDev } from "../targets";

const tc = (s: string) => s.charAt(0) + s.slice(1).toLowerCase();
const captured = (c: ComparisonColumn) =>
  (c.status === "SUCCESS" || c.status === "TRUNCATED") && c.response_text.trim().length > 0;

export default function ComparisonPage() {
  const [questions, setQuestions] = useState<QuestionItem[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [qid, setQid] = useState("");
  const [runId, setRunId] = useState("");
  const [search, setSearch] = useState("");
  const [data, setData] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getQuestions("APPROVED").then((p) => setQuestions(p.questions)).catch((e) => setError(String(e)));
    getRuns()
      .then((r) => {
        setRuns(r);
        if (r.length) setRunId(r[0].run_id);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!qid || !runId) {
      setData(null);
      return;
    }
    let live = true;
    getComparison(qid, runId)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [qid, runId]);

  const matches = useMemo(() => {
    const n = search.trim().toLowerCase();
    const list = n
      ? questions.filter((q) => q.question_text.toLowerCase().includes(n) || q.question_id.toLowerCase().includes(n))
      : questions;
    return list.slice(0, 40);
  }, [questions, search]);

  if (error) return <p className="mt-6 text-neg-ink">Could not load comparison: {error}</p>;

  // If a PROVIDER question has no dev-target column, show an explicit "no response" ghost column.
  const showDevGhost =
    data &&
    data.persona === "PROVIDER" &&
    !data.columns.some((c) => isProviderEvidenceDev(c.llm_name));

  return (
    <div>
      {/* Pickers */}
      <div className="card p-4">
        <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
          <label className="flex min-w-[280px] flex-1 flex-col gap-1">
            <span className="text-[0.7rem] font-bold uppercase tracking-wide text-ink-faint">
              Approved question
            </span>
            <input
              className="field"
              placeholder="Search approved questions…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <Select label="Run" value={runId} onChange={setRunId}>
            {runs.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {r.run_id.slice(0, 8)} · {r.trigger_type}
              </option>
            ))}
          </Select>
        </div>

        {/* Question shortlist */}
        <div className="mt-3 max-h-44 overflow-y-auto rounded-lg border border-hair">
          {matches.length === 0 && <p className="p-3 text-sm text-ink-soft">No approved questions match.</p>}
          {matches.map((q) => (
            <button
              key={q.question_id}
              type="button"
              onClick={() => setQid(q.question_id)}
              className={[
                "flex w-full items-center gap-2 border-b border-hair px-3 py-2 text-left text-sm last:border-0",
                q.question_id === qid ? "bg-brand-soft" : "hover:bg-surface-muted",
              ].join(" ")}
            >
              <span className="tag tag-muted shrink-0">{tc(q.persona)}</span>
              <span className="min-w-0 flex-1 truncate text-ink">{q.question_text}</span>
              <span className="id shrink-0 text-xs text-ink-faint">{q.question_id}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Comparison columns */}
      {!qid ? (
        <p className="mt-6 text-ink-soft">Pick an approved question above to compare model answers.</p>
      ) : !data ? (
        <p className="mt-6 text-ink-soft">Loading comparison…</p>
      ) : (
        <>
          <div className="mt-5">
            <p className="text-lg font-semibold text-ink">{data.question_text || data.question_id}</p>
            <p className="mt-1 text-sm text-ink-soft">{tc(data.persona)} · run {data.run_id.slice(0, 8)}</p>
          </div>

          {data.columns.length === 0 && !showDevGhost ? (
            <p className="mt-6 text-ink-soft">No responses for this question in this run.</p>
          ) : (
            <div className="mt-4 flex gap-4 overflow-x-auto pb-2">
              {data.columns.map((c) => (
                <ColumnCard key={c.response_id} col={c} />
              ))}
              {showDevGhost && <GhostDevColumn />}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ScoreHeader({ col }: { col: ComparisonColumn }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-soft">
      <span>sentiment <SentimentChip value={col.sentiment} /></span>
      {col.competitive_position && (
        <span>· {POSITION_LABELS[col.competitive_position] ?? col.competitive_position}</span>
      )}
      {col.citation_status && <span>· {tc(col.citation_status.replace("_", " "))}</span>}
    </div>
  );
}

function ColumnCard({ col }: { col: ComparisonColumn }) {
  return (
    <div className="card flex w-80 shrink-0 flex-col p-4">
      <div className="font-semibold text-ink">
        <TargetLabel name={col.llm_name} />
      </div>
      <div className="mt-1.5">
        <ScoreHeader col={col} />
      </div>
      <div className="mt-3 max-h-[28rem] overflow-y-auto whitespace-pre-wrap border-t border-hair pt-3 text-sm leading-relaxed text-ink">
        {captured(col) ? (
          col.response_text
        ) : (
          <span className="text-ink-faint">
            no response captured ({col.status}
            {col.block_reason ? ` — ${col.block_reason}` : ""})
          </span>
        )}
      </div>
    </div>
  );
}

/** Honest placeholder when a PROVIDER question has no Provider evidence (dev) answer in this run. */
function GhostDevColumn() {
  return (
    <div className="card flex w-80 shrink-0 flex-col border-dashed p-4">
      <div className="font-semibold text-ink">
        <TargetLabel name={PROVIDER_EVIDENCE_DEV} />
      </div>
      <div className="mt-3 border-t border-hair pt-3 text-sm text-ink-faint">
        no response for this question in this run
      </div>
    </div>
  );
}
