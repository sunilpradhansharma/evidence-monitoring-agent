import { Route, Routes } from "react-router-dom";
import Masthead from "./components/Masthead";
import ReportsView from "./components/reports/ReportsView";
import ApprovalsView from "./components/approvals/ApprovalsView";

export default function App() {
  return (
    <div className="mx-auto w-full max-w-[1180px] px-6 pb-24">
      <Masthead />
      <main className="pt-6">
        <Routes>
          <Route path="/" element={<ReportsView />} />
          <Route path="/approvals" element={<ApprovalsView />} />
          <Route path="*" element={<ReportsView />} />
        </Routes>
      </main>
    </div>
  );
}
