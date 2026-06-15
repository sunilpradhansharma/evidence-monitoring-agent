import { useState } from "react";
import { editQuestion, type QuestionItem } from "../../api";

const PERSONAS = ["PROSPECT", "PROVIDER", "PATIENT"];
const DOMAINS = ["EFFICACY", "SAFETY", "ACCESS", "COMPARATIVE", "GENERAL"];

/** Edit a question via the EXISTING edit endpoint (creates a new version server-side; audited).
 *  Approval state is intentionally not editable here — it moves only through approve/reject. */
export default function EditQuestionModal({
  question,
  onClose,
  onSaved,
}: {
  question: QuestionItem;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [text, setText] = useState(question.question_text);
  const [persona, setPersona] = useState(question.persona);
  const [therapy, setTherapy] = useState(question.therapeutic_area);
  const [brand, setBrand] = useState(question.brand_focus);
  const [domain, setDomain] = useState(question.domain);
  const [active, setActive] = useState(question.active);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await editQuestion(question.question_id, {
        question_text: text.trim(),
        persona,
        therapeutic_area: therapy.trim(),
        brand_focus: brand.trim(),
        domain,
        active,
      });
      onSaved();
    } catch (e) {
      setBusy(false);
      setError(`Could not save: ${String(e)}`);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-ink/30 p-4" onClick={onClose}>
      <div
        className="card w-full max-w-lg p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="section-title">Edit question</h3>
          <span className="id text-xs text-ink-faint">{question.question_id} · v{question.version}</span>
        </div>
        <p className="section-note">Saving creates a new version (the prior version is retained and audited).</p>

        <div className="mt-4 space-y-3">
          <label className="block">
            <span className="text-[0.7rem] font-bold uppercase tracking-wide text-ink-faint">Question text</span>
            <textarea className="field mt-1 h-24 w-full" value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[0.7rem] font-bold uppercase tracking-wide text-ink-faint">Persona</span>
              <select className="field mt-1 w-full" value={persona} onChange={(e) => setPersona(e.target.value)}>
                {PERSONAS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-[0.7rem] font-bold uppercase tracking-wide text-ink-faint">Domain</span>
              <select className="field mt-1 w-full" value={domain} onChange={(e) => setDomain(e.target.value)}>
                {DOMAINS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-[0.7rem] font-bold uppercase tracking-wide text-ink-faint">Therapeutic area</span>
              <input className="field mt-1 w-full" value={therapy} onChange={(e) => setTherapy(e.target.value)} />
            </label>
            <label className="block">
              <span className="text-[0.7rem] font-bold uppercase tracking-wide text-ink-faint">Brand focus</span>
              <input className="field mt-1 w-full" value={brand} onChange={(e) => setBrand(e.target.value)} />
            </label>
          </div>
          <label className="flex items-center gap-2">
            <input type="checkbox" className="h-4 w-4 accent-brand" checked={active} onChange={(e) => setActive(e.target.checked)} />
            <span className="text-sm text-ink-soft">Active (eligible for runs when approved)</span>
          </label>
        </div>

        {error && <p className="mt-3 text-sm text-neg-ink">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button className="btn" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn btn-primary" onClick={save} disabled={busy || !text.trim()}>
            {busy ? "Saving…" : "Save new version"}
          </button>
        </div>
      </div>
    </div>
  );
}
