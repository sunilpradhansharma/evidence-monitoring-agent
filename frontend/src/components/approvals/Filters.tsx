const STATUSES = ["ALL", "PENDING", "APPROVED", "REJECTED"];
const PERSONAS = ["PATIENT", "PROVIDER", "PROSPECT"];

function cap(s: string): string {
  return s.charAt(0) + s.slice(1).toLowerCase();
}

export default function Filters({
  status,
  persona,
  onStatus,
  onPersona,
}: {
  status: string;
  persona: string;
  onStatus: (s: string) => void;
  onPersona: (p: string) => void;
}) {
  return (
    <div className="mt-4 flex flex-wrap items-end gap-3 rounded-xl border border-hair bg-surface p-4 shadow-card">
      <label className="flex flex-col gap-1 text-[0.72rem] font-bold uppercase tracking-wide text-ink-soft">
        Status
        <select className="field" value={status} onChange={(e) => onStatus(e.target.value)}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {cap(s)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-[0.72rem] font-bold uppercase tracking-wide text-ink-soft">
        Persona
        <select className="field" value={persona} onChange={(e) => onPersona(e.target.value)}>
          <option value="">All</option>
          {PERSONAS.map((p) => (
            <option key={p} value={p}>
              {cap(p)}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
