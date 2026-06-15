import ReportsView from "../components/reports/ReportsView";

// Stage 1: the Dashboard route renders the existing run-scoped Reports view so all current
// functionality stays reachable inside the new shell. Stage 2 replaces this with the richer,
// filter-driven dashboard (KPIs, histogram, heatmap, volume-over-time, recent alerts).
export default function DashboardPage() {
  return <ReportsView />;
}
