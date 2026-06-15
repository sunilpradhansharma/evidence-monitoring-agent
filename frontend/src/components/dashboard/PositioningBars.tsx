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
import { isProviderEvidenceDev, targetLabel } from "../../targets";
import { POSITION_COLORS, POSITION_LABELS } from "./colors";

function TargetTick({ x, y, payload }: { x: number; y: number; payload: { value: string } }) {
  const name = payload.value;
  return (
    <text x={x - 6} y={y} dy={4} textAnchor="end" fontSize={11} fill="#5A6675">
      {targetLabel(name)}
      {isProviderEvidenceDev(name) ? "  (dev)" : ""}
    </text>
  );
}

export default function PositioningBars({
  positioning,
}: {
  positioning: Dashboard["positioning"];
}) {
  const reduced = useReducedMotion();
  if (!positioning.series.length) {
    return <p className="text-sm text-ink-soft">No scored responses for these filters.</p>;
  }

  const data = positioning.series.map((s) => {
    const row: Record<string, number | string> = { name: s.target_id };
    for (const pos of positioning.order) {
      const total = s.total || 1;
      row[pos] = Math.round(((s.counts[pos] ?? 0) / total) * 1000) / 10; // % to 0.1
    }
    return row;
  });

  return (
    <div>
      <ResponsiveContainer width="100%" height={Math.max(140, 56 + data.length * 46)}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 16, bottom: 4, left: 96 }}
          stackOffset="expand"
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#E3E8EE" horizontal={false} />
          <XAxis
            type="number"
            domain={[0, 100]}
            tickFormatter={(v) => `${v}%`}
            tick={{ fontSize: 11, fill: "#5A6675" }}
          />
          <YAxis
            type="category"
            dataKey="name"
            tick={(props) => <TargetTick {...props} />}
            width={1}
          />
          <Tooltip
            formatter={(v: number, name: string) => [`${v}%`, POSITION_LABELS[name] ?? name]}
            labelFormatter={(l) => targetLabel(String(l))}
            contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #E3E8EE" }}
          />
          {positioning.order.map((pos) => (
            <Bar
              key={pos}
              dataKey={pos}
              stackId="a"
              fill={POSITION_COLORS[pos]}
              isAnimationActive={!reduced}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {positioning.order.map((pos) => (
          <span key={pos} className="inline-flex items-center gap-1.5 text-xs text-ink-soft">
            <span className="h-3 w-3 rounded-sm" style={{ backgroundColor: POSITION_COLORS[pos] }} />
            {POSITION_LABELS[pos] ?? pos}
          </span>
        ))}
      </div>
    </div>
  );
}
