import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SentimentRow } from "../../api";
import { useReducedMotion } from "../../hooks/useReducedMotion";
import { useTargets } from "../../state/targets";

const POS = "#0F6E56";
const NEG = "#A32D2D";
const NEU = "#5F6B78";

function color(v: number): string {
  if (v >= 0.3) return POS;
  if (v <= -0.3) return NEG;
  return NEU;
}

export default function SentimentChart({ rows }: { rows: SentimentRow[] }) {
  const reduced = useReducedMotion();
  const { labelFor } = useTargets();
  if (!rows.length) return <p className="italic text-ink-soft">No scored responses in view.</p>;
  const data = rows.map((r) => ({
    name: labelFor(r.name),
    value: Number(r.average.toFixed(2)),
    count: r.count,
  }));
  const height = Math.max(120, data.length * 56);

  return (
    <div
      role="img"
      aria-label={
        "Average sentiment by model: " +
        data.map((d) => `${d.name} ${d.value.toFixed(2)}`).join(", ")
      }
      className="card p-3"
    >
      <ResponsiveContainer width="100%" height={height}>
        <BarChart layout="vertical" data={data} margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
          <XAxis
            type="number"
            domain={[-1, 1]}
            ticks={[-1, -0.5, 0, 0.5, 1]}
            tick={{ fontSize: 12, fill: "#5A6675" }}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={140}
            tick={{ fontSize: 12, fill: "#16202B" }}
          />
          <ReferenceLine x={0} stroke="#CFD6DF" />
          <Tooltip
            formatter={(v: number) => [v.toFixed(2), "avg sentiment"]}
            contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #E3E8EE" }}
          />
          <Bar dataKey="value" radius={[4, 4, 4, 4]} isAnimationActive={!reduced}>
            {data.map((d, i) => (
              <Cell key={i} fill={color(d.value)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
