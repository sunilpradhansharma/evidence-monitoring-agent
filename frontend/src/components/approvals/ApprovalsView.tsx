import { useCallback, useEffect, useState } from "react";
import { getQuestions, type QuestionItem, type QuestionsPayload } from "../../api";
import { useReviewer } from "../../state/reviewer";
import Section from "../Section";
import ComplianceBanner from "./ComplianceBanner";
import Filters from "./Filters";
import PendingQueue from "./PendingQueue";
import ReadOnlyTable from "./ReadOnlyTable";
import ReviewerField from "./ReviewerField";
import StatusCounts from "./StatusCounts";

type Counts = QuestionsPayload["counts"];

export default function ApprovalsView() {
  const { reviewer, setReviewer } = useReviewer();
  const [status, setStatus] = useState("ALL");
  const [persona, setPersona] = useState("");
  const [counts, setCounts] = useState<Counts>({ pending: 0, approved: 0, rejected: 0, total: 0 });
  const [pending, setPending] = useState<QuestionItem[]>([]);
  const [approved, setApproved] = useState<QuestionItem[]>([]);
  const [rejected, setRejected] = useState<QuestionItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [p, a, r] = await Promise.all([
        getQuestions("PENDING", persona),
        getQuestions("APPROVED", persona),
        getQuestions("REJECTED", persona),
      ]);
      setPending(p.questions);
      setApproved(a.questions);
      setRejected(r.questions);
      setCounts(p.counts); // counts are global (same across all three responses)
    } catch (e) {
      setError(String(e));
    }
  }, [persona]);

  useEffect(() => {
    load();
  }, [load]);

  const showPending = status === "ALL" || status === "PENDING";
  const showApproved = status === "ALL" || status === "APPROVED";
  const showRejected = status === "ALL" || status === "REJECTED";

  return (
    <div>
      <ComplianceBanner />
      <StatusCounts counts={counts} />
      <ReviewerField value={reviewer} onChange={setReviewer} />
      <Filters status={status} persona={persona} onStatus={setStatus} onPersona={setPersona} />

      {error && <p className="mt-4 text-neg-ink">Could not load questions: {error}</p>}

      {showPending && (
        <Section
          title={`Pending questions — review queue (${pending.length})`}
          note="Each pending question awaits a Medical Affairs decision, grouped by persona. Approving makes it eligible for the next run; rejecting excludes it from all runs. Both are audited."
        >
          <PendingQueue questions={pending} reviewerName={reviewer} onActed={load} />
        </Section>
      )}

      {showApproved && (
        <Section
          title={`Approved questions (${approved.length})`}
          note="Read-only. Currently-approved questions (latest version). To change approval, use the pending queue."
        >
          <ReadOnlyTable questions={approved} emptyText="No approved questions match the current filters." />
        </Section>
      )}

      {showRejected && (
        <Section
          title={`Rejected questions (${rejected.length})`}
          note="Read-only. Excluded from all runs; retained for the audit trail."
        >
          <ReadOnlyTable questions={rejected} emptyText="No rejected questions." />
        </Section>
      )}
    </div>
  );
}
