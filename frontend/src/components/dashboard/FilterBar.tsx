import type { DashTarget } from "../../api";
import TargetLabel from "./TargetLabel";

export interface DashFilterState {
  persona: string;
  therapeutic_area: string;
  period: string;
  llms: string[];
}

interface Props {
  options: { personas: string[]; therapeutic_areas: string[] };
  targets: DashTarget[];
  value: DashFilterState;
  onChange: (next: DashFilterState) => void;
}

function titlecase(s: string): string {
  return s.charAt(0) + s.slice(1).toLowerCase();
}

const PERIODS = [
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
  { value: "all", label: "All" },
];

export default function FilterBar({ options, targets, value, onChange }: Props) {
  const set = (patch: Partial<DashFilterState>) => onChange({ ...value, ...patch });

  const toggleLlm = (id: string) => {
    const next = value.llms.includes(id)
      ? value.llms.filter((l) => l !== id)
      : [...value.llms, id];
    set({ llms: next });
  };

  return (
    <div className="card p-4">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
        {/* Persona */}
        <label className="flex flex-col gap-1">
          <span className="text-[0.7rem] font-bold uppercase tracking-wide text-ink-faint">
            Persona
          </span>
          <select
            className="field min-w-[140px]"
            value={value.persona}
            onChange={(e) => set({ persona: e.target.value })}
          >
            <option value="">All personas</option>
            {options.personas.map((p) => (
              <option key={p} value={p}>
                {titlecase(p)}
              </option>
            ))}
          </select>
        </label>

        {/* Therapy area */}
        <label className="flex flex-col gap-1">
          <span className="text-[0.7rem] font-bold uppercase tracking-wide text-ink-faint">
            Therapy area
          </span>
          <select
            className="field min-w-[150px]"
            value={value.therapeutic_area}
            onChange={(e) => set({ therapeutic_area: e.target.value })}
          >
            <option value="">All areas</option>
            {options.therapeutic_areas.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>

        {/* Period segmented control */}
        <div className="flex flex-col gap-1">
          <span className="text-[0.7rem] font-bold uppercase tracking-wide text-ink-faint">
            Period
          </span>
          <div className="inline-flex overflow-hidden rounded-lg border border-hair">
            {PERIODS.map((p) => (
              <button
                key={p.value}
                type="button"
                onClick={() => set({ period: p.value })}
                className={[
                  "px-3 py-2 text-sm font-semibold transition-colors",
                  value.period === p.value
                    ? "bg-brand text-white"
                    : "bg-surface text-ink-soft hover:bg-surface-muted",
                ].join(" ")}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Target multi-select — all targets are first-class (LLMs + synthesis + provider-api) */}
        <div className="flex flex-col gap-1">
          <span className="text-[0.7rem] font-bold uppercase tracking-wide text-ink-faint">
            Targets {value.llms.length ? `(${value.llms.length})` : "(all)"}
          </span>
          <div className="flex flex-wrap gap-1.5">
            {targets.map((t) => {
              const id = t.target_id;
              const active = value.llms.length === 0 || value.llms.includes(id);
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => toggleLlm(id)}
                  className={[
                    "rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors",
                    active
                      ? "border-brand bg-brand-soft text-brand-dark"
                      : "border-hair bg-surface text-ink-faint hover:bg-surface-muted",
                  ].join(" ")}
                  title={value.llms.length === 0 ? "All targets shown — click to focus on this one" : ""}
                >
                  <TargetLabel name={id} />
                </button>
              );
            })}
            {value.llms.length > 0 && (
              <button
                type="button"
                onClick={() => set({ llms: [] })}
                className="rounded-full px-2 py-1.5 text-xs font-semibold text-ink-soft underline-offset-2 hover:underline"
              >
                clear
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
