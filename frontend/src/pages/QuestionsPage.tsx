import ApprovalsView from "../components/approvals/ApprovalsView";

// Stage 1: the Question Repository route hosts the existing Approvals flow so the Medical Affairs
// approve/reject gate stays reachable and intact inside the new shell. Stage 3 adds the full
// version-aware questions table + Import CSV alongside this approvals flow.
export default function QuestionsPage() {
  return <ApprovalsView />;
}
