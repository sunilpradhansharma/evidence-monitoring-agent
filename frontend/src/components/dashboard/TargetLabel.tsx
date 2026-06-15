import { useTargets } from "../../state/targets";

/** A target's human label, sourced from the backend (config) via TargetsContext. Targets that carry
 *  an explanatory note (e.g. the synthesis target) get a small "ⓘ" info affordance with a tooltip —
 *  NOT a "dev" badge. Every target is presented first-class. */
export default function TargetLabel({ name, className = "" }: { name: string; className?: string }) {
  const { labelFor, noteFor } = useTargets();
  const note = noteFor(name);
  return (
    <span className={`inline-flex items-center gap-1 ${className}`} title={note}>
      <span>{labelFor(name)}</span>
      {note && (
        <span
          aria-label={note}
          className="cursor-help text-[0.7em] font-bold text-ink-faint"
          title={note}
        >
          ⓘ
        </span>
      )}
    </span>
  );
}
