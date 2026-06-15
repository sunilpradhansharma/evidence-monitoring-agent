import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

// The current reviewer's name. There is NO real auth in this phase — this is a simple shared name
// field (persisted locally) that the top bar edits and the Approvals flow reads, so the approver is
// recorded on every approve/reject action (audited server-side). Real auth is a later phase.
interface ReviewerState {
  reviewer: string;
  setReviewer: (name: string) => void;
}

const ReviewerContext = createContext<ReviewerState | null>(null);
const STORAGE_KEY = "em.reviewer";

export function ReviewerProvider({ children }: { children: ReactNode }) {
  const [reviewer, setReviewerState] = useState<string>(
    () => localStorage.getItem(STORAGE_KEY) ?? "",
  );

  useEffect(() => {
    if (reviewer) localStorage.setItem(STORAGE_KEY, reviewer);
    else localStorage.removeItem(STORAGE_KEY);
  }, [reviewer]);

  return (
    <ReviewerContext.Provider value={{ reviewer, setReviewer: setReviewerState }}>
      {children}
    </ReviewerContext.Provider>
  );
}

export function useReviewer(): ReviewerState {
  const ctx = useContext(ReviewerContext);
  if (!ctx) throw new Error("useReviewer must be used within a ReviewerProvider");
  return ctx;
}
