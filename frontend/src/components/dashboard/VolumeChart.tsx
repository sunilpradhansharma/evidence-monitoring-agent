import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Dashboard } from "../../api";
import { useReducedMotion } from "../../hooks/useReducedMotion";
import { STATUS_COLORS, STATUS_ORDER } from "./colors";

export default function VolumeChart({
  weeks,
}: {
  weeks: Dashboard["volume_by_week"];
}) {
  const reduced = useReducedMotion();
  if (!weeks.length) {
    return <p className="text-sm text-ink-soft">No responses captured for these filters.</p>;
  }

  const data = weeks.map((w) => ({
    week: w.week,
    ...Object.fromEntries(STATUS_ORDER.map((s) => [s, w.counts[s] ?? 0])),
  }));

  return (
    <div>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E3E8EE" vertical={false} />
          <XAxis dataKey="week" tick={{ fontSize: 11, fill: "#5A6675" }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#5A6675" }} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #E3E8EE" }} />
          {STATUS_ORDER.map((s) => (
            <Bar
              key={s}
              dataKey={s}
              stackId="vol"
              fill={STATUS_COLORS[s]}
              isAnimationActive={!reduced}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {STATUS_ORDER.map((s) => (
          <span key={s} className="inline-flex items-center gap-1.5 text-xs text-ink-soft">
            <span className="h-3 w-3 rounded-sm" style={{ backgroundColor: STATUS_COLORS[s] }} />
            {s}
          </span>
        ))}
      </div>
    </div>
  );
}
