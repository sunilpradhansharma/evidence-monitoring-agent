import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { getAlerts, getRuns, type RunSummary } from "../../api";
import { timeAgo } from "../../lib/time";
import {
  AlertsIcon,
  CompareIcon,
  DashboardIcon,
  QuestionsIcon,
  ResponsesIcon,
  RunsIcon,
  ShieldIcon,
} from "./icons";
import type { ReactNode } from "react";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  end?: boolean;
  badge?: number;
}

const linkClass = ({ isActive }: { isActive: boolean }) =>
  [
    "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
    isActive
      ? "bg-navy-soft text-white shadow-card"
      : "text-navy-ink hover:bg-navy-soft/60 hover:text-white",
  ].join(" ");

function NavRow({ item }: { item: NavItem }) {
  return (
    <NavLink to={item.to} end={item.end} className={linkClass}>
      {item.icon}
      <span className="flex-1">{item.label}</span>
      {item.badge != null && item.badge > 0 && (
        <span className="rounded-full bg-neg-ink px-2 py-0.5 text-[0.68rem] font-bold leading-none text-white">
          {item.badge}
        </span>
      )}
    </NavLink>
  );
}

function GroupLabel({ children }: { children: ReactNode }) {
  return (
    <p className="mb-1 mt-5 px-3 text-[0.68rem] font-bold uppercase tracking-[0.14em] text-navy-faint">
      {children}
    </p>
  );
}

/** Bottom-of-sidebar run-status chip: "Run in progress" if the latest run is open, else last-run age. */
function RunStatusChip({ runs }: { runs: RunSummary[] }) {
  if (!runs.length) {
    return (
      <div className="rounded-lg border border-navy-line bg-navy-deep px-3 py-2.5 text-xs text-navy-faint">
        No runs yet
      </div>
    );
  }
  const latest = runs[0];
  const running = latest.ended_at == null;
  return (
    <div className="rounded-lg border border-navy-line bg-navy-deep px-3 py-2.5">
      <div className="flex items-center gap-2">
        <span
          className={[
            "h-2 w-2 rounded-full",
            running ? "animate-pulse bg-amber-400" : "bg-emerald-400",
          ].join(" ")}
        />
        <span className="text-xs font-semibold text-white">
          {running ? "Run in progress" : "Idle"}
        </span>
      </div>
      <p className="mt-1 text-[0.7rem] text-navy-faint">
        {running
          ? `started ${timeAgo(latest.started_at)}`
          : `last run ${timeAgo(latest.ended_at)}`}
      </p>
    </div>
  );
}

export default function Sidebar() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [alertCount, setAlertCount] = useState(0);

  useEffect(() => {
    getRuns()
      .then(setRuns)
      .catch(() => setRuns([]));
    getAlerts()
      .then((a) => setAlertCount(a.length))
      .catch(() => setAlertCount(0));
  }, []);

  const insights: NavItem[] = [
    { to: "/", label: "Dashboard", icon: <DashboardIcon />, end: true },
    { to: "/responses", label: "Responses", icon: <ResponsesIcon /> },
    { to: "/alerts", label: "Alerts", icon: <AlertsIcon />, badge: alertCount },
    { to: "/comparison", label: "LLM Comparison", icon: <CompareIcon /> },
  ];
  const manage: NavItem[] = [
    { to: "/questions", label: "Question Repository", icon: <QuestionsIcon /> },
    { to: "/runs", label: "Runs", icon: <RunsIcon /> },
  ];

  return (
    <aside className="fixed inset-y-0 left-0 z-20 flex w-[252px] flex-col bg-navy px-4 py-5 text-navy-ink">
      {/* Brand */}
      <div className="flex items-center gap-3 px-1">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand text-white shadow-card">
          <ShieldIcon />
        </span>
        <div className="leading-tight">
          <p className="text-[0.95rem] font-extrabold tracking-tight text-white">Evidence Monitor</p>
          <p className="text-[0.7rem] font-medium text-navy-faint">AI Response Intelligence</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="mt-4 flex-1 overflow-y-auto" aria-label="Primary">
        <GroupLabel>Insights</GroupLabel>
        <div className="space-y-0.5">
          {insights.map((item) => (
            <NavRow key={item.to} item={item} />
          ))}
        </div>
        <GroupLabel>Manage</GroupLabel>
        <div className="space-y-0.5">
          {manage.map((item) => (
            <NavRow key={item.to} item={item} />
          ))}
        </div>
      </nav>

      {/* Run status */}
      <div className="mt-3">
        <RunStatusChip runs={runs} />
      </div>
    </aside>
  );
}
