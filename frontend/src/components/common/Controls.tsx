import type { ReactNode } from "react";

export function Select({
  label,
  value,
  onChange,
  children,
  className = "",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[0.7rem] font-bold uppercase tracking-wide text-ink-faint">{label}</span>
      <select className={`field ${className}`} value={value} onChange={(e) => onChange(e.target.value)}>
        {children}
      </select>
    </label>
  );
}

const PERIODS = [
  { v: "7d", l: "7d" },
  { v: "30d", l: "30d" },
  { v: "all", l: "All" },
];

export function Segmented({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[0.7rem] font-bold uppercase tracking-wide text-ink-faint">Period</span>
      <div className="inline-flex overflow-hidden rounded-lg border border-hair">
        {PERIODS.map((o) => (
          <button
            key={o.v}
            type="button"
            onClick={() => onChange(o.v)}
            className={[
              "px-3 py-2 text-sm font-semibold transition-colors",
              value === o.v ? "bg-brand text-white" : "bg-surface text-ink-soft hover:bg-surface-muted",
            ].join(" ")}
          >
            {o.l}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Th({ children }: { children: ReactNode }) {
  return <th className="px-4 py-2.5 font-bold">{children}</th>;
}

export function Td({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <td className={`px-4 py-3 align-top ${className}`}>{children}</td>;
}
