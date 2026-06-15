// Lightweight inline stroke icons for the sidebar nav. `currentColor` so they inherit nav text
// color (active vs idle). 24x24 viewBox, 1.8 stroke — quiet and clinical.
import type { ReactNode } from "react";

function Svg({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-[18px] w-[18px] shrink-0"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export function DashboardIcon() {
  return (
    <Svg>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </Svg>
  );
}

export function ResponsesIcon() {
  return (
    <Svg>
      <path d="M4 5h16M4 10h16M4 15h10M4 20h7" />
    </Svg>
  );
}

export function AlertsIcon() {
  return (
    <Svg>
      <path d="M12 4a5 5 0 0 0-5 5c0 4-1.5 6-2 7h14c-.5-1-2-3-2-7a5 5 0 0 0-5-5z" />
      <path d="M10 20a2 2 0 0 0 4 0" />
    </Svg>
  );
}

export function CompareIcon() {
  return (
    <Svg>
      <path d="M12 4v16" />
      <rect x="3" y="7" width="6" height="10" rx="1.5" />
      <rect x="15" y="7" width="6" height="10" rx="1.5" />
    </Svg>
  );
}

export function QuestionsIcon() {
  return (
    <Svg>
      <path d="M5 4h11l3 3v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z" />
      <path d="M9.2 9.2a2.5 2.5 0 0 1 4.3 1.7c0 1.7-2.5 2-2.5 3.6" />
      <path d="M11 17.5h.01" />
    </Svg>
  );
}

export function RunsIcon() {
  return (
    <Svg>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </Svg>
  );
}

export function ShieldIcon() {
  return (
    <Svg>
      <path d="M12 3l8 4v5c0 4.4-3.1 7.9-8 9-4.9-1.1-8-4.6-8-9V7l8-4z" />
      <path d="M8 12l2.5 2.5L16 9" />
    </Svg>
  );
}
