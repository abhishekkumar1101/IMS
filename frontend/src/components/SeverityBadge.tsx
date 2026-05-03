import type { Severity } from "../lib/types";

const COLORS: Record<Severity, string> = {
  P0: "bg-rose-50 text-rose-700 border-rose-200",
  P1: "bg-orange-50 text-orange-700 border-orange-200",
  P2: "bg-amber-50 text-amber-700 border-amber-200",
  P3: "bg-blue-50 text-blue-700 border-blue-200",
};

export function SeverityBadge({ sev }: { sev: Severity }) {
  return (
    <span className={`pill ${COLORS[sev]}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {sev}
    </span>
  );
}
