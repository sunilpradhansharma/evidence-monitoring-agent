import { NavLink } from "react-router-dom";

function ShieldIcon() {
  return (
    <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-white shadow-card">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-5 w-5"
        aria-hidden="true"
      >
        <path d="M12 3l8 4v5c0 4.4-3.1 7.9-8 9-4.9-1.1-8-4.6-8-9V7l8-4z" />
        <path d="M8 12l2.5 2.5L16 9" />
      </svg>
    </span>
  );
}

export default function Masthead() {
  const tab = ({ isActive }: { isActive: boolean }) =>
    [
      "rounded-t-md border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors",
      isActive
        ? "border-brand text-brand"
        : "border-transparent text-ink-soft hover:bg-brand-soft hover:text-ink",
    ].join(" ");

  return (
    <header>
      <div className="flex items-center gap-3 pt-7">
        <ShieldIcon />
        <h1 className="text-[1.7rem] font-extrabold tracking-tight text-ink">
          Evidence Monitoring AI Agent
        </h1>
      </div>
      <p className="mt-2 max-w-[72ch] text-[0.97rem] text-ink-soft">
        How public AI models represent the therapy versus competitors. Only approved questions are
        sent; a human approves every question.
      </p>
      <nav className="mt-5 flex gap-1 border-b border-hair" aria-label="Primary">
        <NavLink to="/" end className={tab}>
          Reports
        </NavLink>
        <NavLink to="/approvals" className={tab}>
          Approvals
        </NavLink>
      </nav>
    </header>
  );
}
