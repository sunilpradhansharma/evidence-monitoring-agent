import { Outlet, useLocation } from "react-router-dom";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";

// Page chrome (title + subtitle) per route prefix. Kept here so the top bar stays in sync with the
// sidebar without each page re-declaring it.
const PAGES: { match: (p: string) => boolean; title: string; subtitle: string }[] = [
  {
    match: (p) => p === "/",
    title: "Dashboard",
    subtitle: "How public AI models represent the therapy versus competitors.",
  },
  {
    match: (p) => p.startsWith("/responses"),
    title: "Responses",
    subtitle: "Every captured model answer, filterable and exportable.",
  },
  {
    match: (p) => p.startsWith("/alerts"),
    title: "Alerts",
    subtitle: "Flagged responses raised by deterministic threshold rules.",
  },
  {
    match: (p) => p.startsWith("/comparison"),
    title: "LLM Comparison",
    subtitle: "Compare how each model answered the same approved question.",
  },
  {
    match: (p) => p.startsWith("/questions") || p.startsWith("/approvals"),
    title: "Question Repository",
    subtitle: "Curated, versioned questions and the Medical Affairs approval gate.",
  },
  {
    match: (p) => p.startsWith("/runs"),
    title: "Runs",
    subtitle: "Run history — capture, alerts, tokens, and cost per run.",
  },
];

export default function AppLayout() {
  const { pathname } = useLocation();
  const page = PAGES.find((p) => p.match(pathname)) ?? PAGES[0];

  return (
    <div className="min-h-screen bg-page">
      <Sidebar />
      <div className="pl-[252px]">
        <Topbar title={page.title} subtitle={page.subtitle} />
        <main className="px-8 pb-24 pt-6">
          <div className="mx-auto w-full max-w-[1280px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
