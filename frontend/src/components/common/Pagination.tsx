interface Props {
  page: number;
  pageSize: number;
  total: number;
  onPage: (p: number) => void;
  onPageSize?: (n: number) => void;
}

const SIZES = [10, 25, 50, 100];

/** "X–Y of Z" with prev/next and an optional rows-per-page control. */
export default function Pagination({ page, pageSize, total, onPage, onPageSize }: Props) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);

  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm text-ink-soft">
      <span className="tabular-nums">
        {from}–{to} of {total.toLocaleString()}
      </span>
      <div className="flex items-center gap-3">
        {onPageSize && (
          <label className="flex items-center gap-1.5">
            <span className="text-xs">Rows</span>
            <select
              className="field py-1"
              value={pageSize}
              onChange={(e) => onPageSize(Number(e.target.value))}
            >
              {SIZES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="btn px-3 py-1.5"
            disabled={page <= 1}
            onClick={() => onPage(page - 1)}
          >
            ← Prev
          </button>
          <span className="px-2 tabular-nums">
            {page} / {pages}
          </span>
          <button
            type="button"
            className="btn px-3 py-1.5"
            disabled={page >= pages}
            onClick={() => onPage(page + 1)}
          >
            Next →
          </button>
        </div>
      </div>
    </div>
  );
}
