import type { Report } from "../../api";
import { targetLabel } from "../../targets";

function short(pos: string): string {
  return pos.toLowerCase().replace(/_/g, " ");
}

export default function PositioningTable({ positioning }: { positioning: Report["positioning"] }) {
  const { order, rows } = positioning;
  if (!rows.length) return <p className="italic text-ink-soft">No scored responses in view.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full overflow-hidden rounded-xl border border-hair text-sm shadow-card">
        <thead>
          <tr className="bg-surface-muted">
            <th className="border-b border-hair px-3 py-2 text-left text-xs font-bold uppercase tracking-wide">
              Model
            </th>
            {order.map((p) => (
              <th
                key={p}
                className="border-b border-hair px-3 py-2 text-right text-xs font-bold uppercase tracking-wide"
              >
                {short(p)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.model} className="hover:bg-brand-soft">
              <td className="border-b border-hair px-3 py-2 font-medium">{targetLabel(row.model)}</td>
              {order.map((p) => (
                <td key={p} className="border-b border-hair px-3 py-2 text-right tabular-nums">
                  {row.counts[p] ?? 0}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
