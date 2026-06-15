import { Route, Routes } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout";
import DashboardPage from "./pages/DashboardPage";
import ResponsesPage from "./pages/ResponsesPage";
import AlertsPage from "./pages/AlertsPage";
import ComparisonPage from "./pages/ComparisonPage";
import QuestionsPage from "./pages/QuestionsPage";
import RunsPage from "./pages/RunsPage";
import { ReviewerProvider } from "./state/reviewer";

export default function App() {
  return (
    <ReviewerProvider>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/responses" element={<ResponsesPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/comparison" element={<ComparisonPage />} />
          <Route path="/questions" element={<QuestionsPage />} />
          {/* Keep the old direct Approvals path working; it lives under Question Repository now. */}
          <Route path="/approvals" element={<QuestionsPage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="*" element={<DashboardPage />} />
        </Route>
      </Routes>
    </ReviewerProvider>
  );
}
