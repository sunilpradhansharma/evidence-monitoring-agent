import { useCallback, useEffect, useMemo, useState } from "react";
import { getQuestions, type QuestionItem, type QuestionsPayload } from "../api";
import ApprovalsView from "../components/approvals/ApprovalsView";
import { Select, Td, Th } from "../components/common/Controls";
import EditQuestionModal from "../components/questions/EditQuestionModal";
import { shortDateTime } from "../lib/time";

const PERSONAS = ["PROSPECT", "PROVIDER", "PATIENT"];
const DOMAINS = ["EFFICACY", "SAFETY", "ACCESS", "COMPARATIVE", "GENERAL"];
const STATUSES = ["PENDING", "APPROVED", "REJECTED"];
const tc = (s: string) => s.charAt(0) + s.slice(1).toLowerCase();

const STATUS_TONE: Record<string, string> = {
  PENDING: "border-part-ink/30 bg-part-bg text-part-ink",
  APPROVED: "border-fav-ink/30 bg-fav-bg text-fav-ink",
  REJECTED: "border-neg-ink/30 bg-neg-bg text-neg-ink",
};

export default function QuestionsPage() {
  const [tab, setTab] = useState<"repo" | "approvals">("repo");
  const [counts, setCounts] = useState<QuestionsPayload["counts"]>({ pending: 0, approved: 0, rejected: 0, total: 0 });
  const [rows, setRows] = useState<QuestionItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<QuestionItem | null>(null);
  const [showImport, setShowImport] = useState(false);

  const [persona, setPersona] = useState("");
  const [domain, setDomain] = useState("");
  const [approval, setApproval] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    try {
      const payload = await getQuestions("ALL");
      setRows(payload.questions);
      setCounts(payload.counts);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const n = search.trim().toLowerCase();
    return rows.filter(
      (q) =>
        (!persona || q.persona === persona) &&
        (!domain || q.domain === domain) &&
        (!approval || q.approval_status === approval) &&
        (!activeOnly || q.active) &&
        (!n || q.question_id.toLowerCase().includes(n) || q.question_text.toLowerCase().includes(n)),
    );
  }, [rows, persona, domain, approval, activeOnly, search]);

  if (error) return <p className="mt-6 text-neg-ink">Could not load questions: {error}</p>;

  return (
    <div>
      {/* Sub-tabs: the version-aware repository table + the existing approval gate */}
      <div className="flex items-center gap-1 border-b border-hair">
        <SubTab active={tab === "repo"} onClick={() => setTab("repo")}>
          Repository ({counts.total})
        </SubTab>
        <SubTab active={tab === "approvals"} onClick={() => setTab("approvals")}>
          Approvals ({counts.pending} pending)
        </SubTab>
      </div>

      {tab === "approvals" ? (
        <div className="mt-4">
          <ApprovalsView />
        </div>
      ) : (
        <div className="mt-4">
          {/* Toolbar */}
          <div className="card p-4">
            <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
              <input
                className="field min-w-[220px] flex-1"
                placeholder="Search question text or id…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <Select label="Persona" value={persona} onChange={setPersona}>
                <option value="">All</option>
                {PERSONAS.map((p) => <option key={p} value={p}>{tc(p)}</option>)}
              </Select>
              <Select label="Domain" value={domain} onChange={setDomain}>
                <option value="">All</option>
                {DOMAINS.map((d) => <option key={d} value={d}>{tc(d)}</option>)}
              </Select>
              <Select label="Approval" value={approval} onChange={setApproval}>
                <option value="">All</option>
                {STATUSES.map((s) => <option key={s} value={s}>{tc(s)}</option>)}
              </Select>
              <label className="flex items-center gap-2 self-end pb-2">
                <input type="checkbox" className="h-4 w-4 accent-brand" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} />
                <span className="text-sm text-ink-soft">Active only</span>
              </label>
              <div className="ml-auto flex items-end gap-2">
                <button className="btn" onClick={() => setShowImport(true)}>Import CSV</button>
                <button className="btn" disabled title="Question authoring form is a later phase">
                  + Add question
                </button>
              </div>
            </div>
          </div>

          {/* Table */}
          <div className="card mt-4 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hair bg-surface-muted text-left text-[0.7rem] uppercase tracking-wide text-ink-faint">
                    <Th>Question</Th>
                    <Th>Persona</Th>
                    <Th>Therapy</Th>
                    <Th>Brand / Domain</Th>
                    <Th>Approval</Th>
                    <Th>Ver</Th>
                    <Th>Active</Th>
                    <Th>Updated</Th>
                    <Th> </Th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((q) => (
                    <tr key={q.question_id} className="border-b border-hair last:border-0 hover:bg-brand-soft/30">
                      <Td>
                        <span className="font-medium text-ink">{q.question_text}</span>
                        <span className="id mt-0.5 block text-xs text-ink-faint">{q.question_id}</span>
                      </Td>
                      <Td>{tc(q.persona)}</Td>
                      <Td className="text-ink-soft">{q.therapeutic_area}</Td>
                      <Td className="text-ink-soft">{q.brand_focus} · {tc(q.domain)}</Td>
                      <Td><span className={`pill ${STATUS_TONE[q.approval_status] ?? ""}`}>{tc(q.approval_status)}</span></Td>
                      <Td className="tabular-nums text-ink-soft">v{q.version}</Td>
                      <Td>{q.active ? <span className="text-fav-ink">●</span> : <span className="text-ink-faint">○</span>}</Td>
                      <Td className="whitespace-nowrap text-ink-faint">{shortDateTime(q.updated_at)}</Td>
                      <Td>
                        <button className="font-semibold text-brand hover:underline" onClick={() => setEditing(q)}>Edit</button>
                      </Td>
                    </tr>
                  ))}
                  {filtered.length === 0 && (
                    <tr><td colSpan={9} className="p-8 text-center text-ink-soft">No questions match these filters.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {editing && (
        <EditQuestionModal
          question={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
      {showImport && <ImportModal onClose={() => setShowImport(false)} />}
    </div>
  );
}

function SubTab({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors",
        active ? "border-brand text-brand" : "border-transparent text-ink-soft hover:text-ink",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

/** Import is performed by the existing CLI importer (no HTTP write path is added in this phase). */
function ImportModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-ink/30 p-4" onClick={onClose}>
      <div className="card w-full max-w-lg p-5" onClick={(e) => e.stopPropagation()}>
        <h3 className="section-title">Import questions (CSV)</h3>
        <p className="section-note">
          Curation import runs through the existing CLI importer (questions are imported as PENDING,
          then reviewed under Approvals). Run:
        </p>
        <pre className="mt-3 overflow-x-auto rounded-lg bg-ink p-3 text-xs text-white">
          uv run evidence-monitor import-questions data/question_bank.csv
        </pre>
        <p className="mt-2 text-xs text-ink-soft">
          A browser upload endpoint is a later phase — this dashboard stays read-only except for the
          audited approve / reject / edit actions.
        </p>
        <div className="mt-5 flex justify-end">
          <button className="btn btn-primary" onClick={onClose}>Got it</button>
        </div>
      </div>
    </div>
  );
}
