import { useState } from "react";
import { useReviewer } from "../../state/reviewer";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

/** Top bar: page title on the left, the current reviewer (editable name + sign-out placeholder) on
 *  the right. NO real auth this phase — the name is just recorded on approve/reject actions. */
export default function Topbar({ title, subtitle }: { title: string; subtitle?: string }) {
  const { reviewer, setReviewer } = useReviewer();
  const [editing, setEditing] = useState(false);

  return (
    <header className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-hair bg-page/85 px-8 py-4 backdrop-blur">
      <div className="min-w-0">
        <h1 className="truncate text-[1.35rem] font-extrabold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="truncate text-sm text-ink-soft">{subtitle}</p>}
      </div>

      <div className="flex items-center gap-3">
        {editing || !reviewer ? (
          <input
            autoFocus
            className="field w-48"
            placeholder="Your name (reviewer)"
            value={reviewer}
            onChange={(e) => setReviewer(e.target.value)}
            onBlur={() => setEditing(false)}
            onKeyDown={(e) => e.key === "Enter" && setEditing(false)}
            aria-label="Reviewer name"
          />
        ) : (
          <button
            type="button"
            className="flex items-center gap-2.5 rounded-lg border border-hair bg-surface px-2.5 py-1.5 text-left transition-colors hover:bg-surface-muted"
            onClick={() => setEditing(true)}
            title="Click to change reviewer"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-soft text-xs font-bold text-brand-dark">
              {initials(reviewer)}
            </span>
            <span className="leading-tight">
              <span className="block text-sm font-semibold text-ink">{reviewer}</span>
              <span className="block text-[0.7rem] text-ink-faint">Reviewer</span>
            </span>
          </button>
        )}
        <button
          type="button"
          className="btn text-ink-soft"
          onClick={() => setReviewer("")}
          title="Sign out (placeholder — no auth in this phase)"
          disabled={!reviewer}
        >
          Sign out
        </button>
      </div>
    </header>
  );
}
