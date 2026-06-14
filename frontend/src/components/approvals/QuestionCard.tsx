import { useState } from "react";
import { approveQuestion, rejectQuestion, type QuestionItem } from "../../api";
import { useReducedMotion } from "../../hooks/useReducedMotion";

export default function QuestionCard({
  q,
  reviewerName,
  onActed,
}: {
  q: QuestionItem;
  reviewerName: string;
  onActed: () => void;
}) {
  const reduced = useReducedMotion();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = reviewerName.trim().length > 0;

  function finish() {
    if (reduced) {
      onActed();
      return;
    }
    setLeaving(true);
    window.setTimeout(onActed, 280);
  }

  async function act(kind: "approve" | "reject") {
    if (!ready || busy) return;
    if (kind === "reject" && !reason.trim()) {
      setError("A reason is required to reject.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (kind === "approve") await approveQuestion(q.question_id, reviewerName.trim());
      else await rejectQuestion(q.question_id, reviewerName.trim(), reason.trim());
      finish();
    } catch (e) {
      setBusy(false);
      setError(`Could not ${kind}: ${String(e)}`);
    }
  }

  return (
    <div
      className={`card lift p-5 transition-all duration-300 ease-spring ${
        leaving ? "translate-x-3 opacity-0" : "opacity-100"
      }`}
      data-question-id={q.question_id}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="id font-extrabold">{q.question_id}</span>
        <span className="tag">{q.persona.toLowerCase()}</span>
        <span className="tag tag-muted">{q.therapeutic_area}</span>
        <span className="tag tag-muted">{q.domain.toLowerCase()}</span>
      </div>
      <p className="my-2 text-[0.98rem] leading-relaxed text-ink">{q.question_text}</p>
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          className="field w-full"
          placeholder="rationale / rejection reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          aria-label={`Rationale for ${q.question_id}`}
        />
        <button
          className="btn btn-good min-w-[100px]"
          disabled={!ready || busy}
          onClick={() => act("approve")}
        >
          Approve
        </button>
        <button
          className="btn btn-danger min-w-[100px]"
          disabled={!ready || busy}
          onClick={() => act("reject")}
        >
          Reject
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-neg-ink">{error}</p>}
    </div>
  );
}
