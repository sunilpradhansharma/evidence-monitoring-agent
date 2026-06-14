import type { QuestionItem } from "../../api";
import QuestionCard from "./QuestionCard";

const PERSONA_ORDER = ["PATIENT", "PROVIDER", "PROSPECT"];

function cap(s: string): string {
  return s.charAt(0) + s.slice(1).toLowerCase();
}

export default function PendingQueue({
  questions,
  reviewerName,
  onActed,
}: {
  questions: QuestionItem[];
  reviewerName: string;
  onActed: () => void;
}) {
  if (!questions.length) {
    return <p className="italic text-ink-soft">No pending questions match the current filters.</p>;
  }
  const groups = PERSONA_ORDER.map((p) => ({
    persona: p,
    items: questions.filter((q) => q.persona === p),
  })).filter((g) => g.items.length > 0);

  return (
    <div>
      {groups.map((g) => (
        <div key={g.persona}>
          <div className="mt-6 flex items-baseline gap-2 border-b-2 border-hair pb-1.5">
            <h3 className="text-base font-extrabold tracking-tight text-ink">{cap(g.persona)}</h3>
            <span className="text-sm text-ink-soft">{g.items.length} pending</span>
          </div>
          <div className="mt-2 space-y-2.5">
            {g.items.map((q) => (
              <QuestionCard
                key={q.question_id}
                q={q}
                reviewerName={reviewerName}
                onActed={onActed}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
