import TargetLabel from "./TargetLabel";

/** Color-swatch legend for per-target chart series, with the dev badge on the dev stand-in. */
export default function SeriesLegend({
  items,
}: {
  items: { targetId: string; color: string }[];
}) {
  return (
    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
      {items.map((it) => (
        <span key={it.targetId} className="inline-flex items-center gap-1.5 text-xs text-ink-soft">
          <span className="h-3 w-3 rounded-sm" style={{ backgroundColor: it.color }} />
          <TargetLabel name={it.targetId} />
        </span>
      ))}
    </div>
  );
}
