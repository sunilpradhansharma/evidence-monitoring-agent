import type { Dashboard } from "../../api";
import { sentimentColor, sentimentTextColor } from "./colors";
import TargetLabel from "./TargetLabel";

export default function SentimentHeatmap({
  heatmap,
  onCell,
}: {
  heatmap: Dashboard["heatmap"];
  onCell: (targetId: string, therapeuticArea: string) => void;
}) {
  const areas = heatmap.therapeutic_areas;
  if (!heatmap.rows.length || !areas.length) {
    return <p className="text-sm text-ink-soft">No scored responses for these filters.</p>;
  }

  const cols = `minmax(150px, 1.4fr) repeat(${areas.length}, minmax(72px, 1fr))`;

  return (
    <div>
      <div className="overflow-x-auto">
        <div className="grid gap-1" style={{ gridTemplateColumns: cols, minWidth: 360 }}>
          {/* header row */}
          <div />
          {areas.map((a) => (
            <div
              key={a}
              className="truncate px-1 pb-1 text-center text-[0.7rem] font-bold uppercase tracking-wide text-ink-faint"
              title={a}
            >
              {a}
            </div>
          ))}

          {/* data rows */}
          {heatmap.rows.map((row) => (
            <FragmentRow key={row.target_id} row={row} onCell={onCell} />
          ))}
        </div>
      </div>

      {/* Legend: -1 (red) → +1 (green) */}
      <div className="mt-4 flex items-center gap-3 text-xs text-ink-soft">
        <span>−1.0</span>
        <span
          className="h-3 w-40 rounded"
          style={{
            background: `linear-gradient(to right, ${sentimentColor(-1)}, ${sentimentColor(0)}, ${sentimentColor(1)})`,
          }}
        />
        <span>+1.0</span>
        <span className="ml-2 inline-flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm border border-hair bg-surface-muted" /> n/a (no data)
        </span>
      </div>
    </div>
  );
}

function FragmentRow({
  row,
  onCell,
}: {
  row: Dashboard["heatmap"]["rows"][number];
  onCell: (targetId: string, therapeuticArea: string) => void;
}) {
  return (
    <>
      <div className="flex items-center pr-2 text-sm text-ink">
        <TargetLabel name={row.target_id} />
      </div>
      {row.cells.map((c) => {
        if (c.mean === null) {
          return (
            <div
              key={c.therapeutic_area}
              className="flex h-11 items-center justify-center rounded-md border border-hair bg-surface-muted text-xs text-ink-faint"
              title="no data for this LLM × therapy area"
            >
              n/a
            </div>
          );
        }
        return (
          <button
            key={c.therapeutic_area}
            type="button"
            onClick={() => onCell(row.target_id, c.therapeutic_area)}
            className="flex h-11 items-center justify-center rounded-md text-xs font-bold tabular-nums transition-transform hover:scale-[1.04]"
            style={{ backgroundColor: sentimentColor(c.mean), color: sentimentTextColor(c.mean) }}
            title={`${row.target_id} · ${c.therapeutic_area}: mean ${c.mean >= 0 ? "+" : ""}${c.mean.toFixed(2)} over ${c.count} response${c.count === 1 ? "" : "s"} — click to drill in`}
          >
            {c.mean >= 0 ? "+" : ""}
            {c.mean.toFixed(2)}
          </button>
        );
      })}
    </>
  );
}
