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
import { useTargets } from "../../state/targets";
import { seriesColor } from "./colors";
import SeriesLegend from "./SeriesLegend";

export default function SentimentHistogram({
  histogram,
}: {
  histogram: Dashboard["sentiment_histogram"];
}) {
  const reduced = useReducedMotion();
  const { labelFor } = useTargets();
  const edges = histogram.bucket_edges;

  // Every target is first-class — assign palette colors by series order (no special "dev" color).
  const colored = histogram.series.map((s, i) => ({ ...s, color: seriesColor(i) }));

  if (!colored.length) {
    return <p className="text-sm text-ink-soft">No scored responses for these filters.</p>;
  }

  const data = Array.from({ length: edges.length - 1 }, (_, i) => {
    const row: Record<string, number | string> = {
      bucket: `${edges[i] > 0 ? "+" : ""}${edges[i].toFixed(2)}`,
    };
    for (const s of colored) row[s.target_id] = s.counts[i] ?? 0;
    return row;
  });

  return (
    <div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E3E8EE" vertical={false} />
          <XAxis dataKey="bucket" tick={{ fontSize: 11, fill: "#5A6675" }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#5A6675" }} />
          <Tooltip
            formatter={(v: number, name: string) => [v, labelFor(name)]}
            labelFormatter={(l) => `sentiment ≈ ${l}`}
            contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #E3E8EE" }}
          />
          {colored.map((s) => (
            <Bar
              key={s.target_id}
              dataKey={s.target_id}
              fill={s.color}
              radius={[2, 2, 0, 0]}
              isAnimationActive={!reduced}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
      <SeriesLegend items={colored.map((s) => ({ targetId: s.target_id, color: s.color }))} />
    </div>
  );
}
