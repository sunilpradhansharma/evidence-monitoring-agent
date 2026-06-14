import type { Report } from "../../api";
import { cellStyle, CELL_STYLES, LEGEND_ORDER } from "./cells";

export default function CoverageMap({
  coverage,
  onOpen,
}: {
  coverage: Report["coverage"];
  onOpen: (responseId: string) => void;
}) {
  const { models, rows } = coverage;
  if (!rows.length || !models.length) {
    return <p className="italic text-ink-soft">No responses in view.</p>;
  }
  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-ink-soft">
        {LEGEND_ORDER.map((k) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className={`h-3.5 w-3.5 rounded ${CELL_STYLES[k].swatch}`} />
            {CELL_STYLES[k].legend}
          </span>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-separate" style={{ borderSpacing: "5px" }}>
          <thead>
            <tr>
              <th className="w-[30%] px-2 pb-2 text-left text-xs font-bold text-ink-soft">
                Question
              </th>
              {models.map((m) => (
                <th key={m} className="px-2 pb-2 text-center text-sm font-bold text-ink">
                  {m}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.question_id}>
                <td className="rounded-lg border border-hair bg-surface px-3 py-2 align-middle text-sm leading-snug">
                  <span className="block text-xs font-bold text-ink">{row.question_id}</span>
                  <span className="text-ink-soft">{row.label}</span>
                </td>
                {row.cells.map((cell, i) => {
                  const s = cellStyle(cell.klass);
                  const clickable = Boolean(cell.response_id);
                  const inner = (
                    <>
                      {cell.label}
                      {cell.truncated && (
                        <span className="absolute right-1 top-1 rounded border border-dashed border-part-ink px-1 text-[0.55rem] font-bold leading-none text-part-ink">
                          trunc
                        </span>
                      )}
                    </>
                  );
                  return (
                    <td key={i} className="p-0">
                      {clickable ? (
                        <button
                          type="button"
                          onClick={() => onOpen(cell.response_id!)}
                          title={cell.title}
                          aria-label={`${row.question_id} × ${models[i]}: ${cell.label}`}
                          className={`relative flex h-12 w-full items-center justify-center rounded-lg px-2 text-sm font-bold transition-transform hover:-translate-y-0.5 hover:shadow-lift focus:outline-none focus:ring-2 focus:ring-brand ${s.box}`}
                        >
                          {inner}
                        </button>
                      ) : (
                        <span
                          title={cell.title}
                          className={`relative flex h-12 w-full items-center justify-center rounded-lg px-2 text-sm font-bold ${s.box}`}
                        >
                          {inner}
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
