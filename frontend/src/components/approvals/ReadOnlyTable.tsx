import type { QuestionItem } from "../../api";

export default function ReadOnlyTable({
  questions,
  emptyText,
}: {
  questions: QuestionItem[];
  emptyText: string;
}) {
  if (!questions.length) return <p className="italic text-ink-soft">{emptyText}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full overflow-hidden rounded-xl border border-hair text-sm shadow-card">
        <thead>
          <tr className="bg-surface-muted text-left text-xs font-bold uppercase tracking-wide">
            <th className="border-b border-hair px-3 py-2">Question id</th>
            <th className="border-b border-hair px-3 py-2">Persona</th>
            <th className="border-b border-hair px-3 py-2">Question</th>
            <th className="border-b border-hair px-3 py-2">Approver</th>
            <th className="border-b border-hair px-3 py-2">Updated (UTC)</th>
          </tr>
        </thead>
        <tbody>
          {questions.map((q) => (
            <tr key={q.question_id} className="align-top hover:bg-brand-soft">
              <td className="border-b border-hair px-3 py-2 font-semibold">{q.question_id}</td>
              <td className="border-b border-hair px-3 py-2">{q.persona.toLowerCase()}</td>
              <td className="border-b border-hair px-3 py-2">{q.question_text}</td>
              <td className="border-b border-hair px-3 py-2">{q.approver_name ?? "—"}</td>
              <td className="border-b border-hair px-3 py-2 tabular-nums text-ink-soft">
                {q.updated_at ? q.updated_at.replace("T", " ").slice(0, 16) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
