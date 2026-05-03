import type { IncidentState } from "../lib/types";

const STAGES: IncidentState[] = ["OPEN", "INVESTIGATING", "RESOLVED", "CLOSED"];

export function StateStepper({ state }: { state: IncidentState }) {
  const idx = STAGES.indexOf(state);
  return (
    <div className="flex items-center gap-1">
      {STAGES.map((s, i) => {
        const active = i <= idx;
        const current = i === idx;
        return (
          <div key={s} className="flex items-center gap-1">
            <div
              className={`text-[10px] font-medium px-2 py-0.5 rounded uppercase tracking-wide transition ${
                current
                  ? "bg-blue-600 text-white border border-blue-600"
                  : active
                  ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                  : "bg-slate-50 text-slate-400 border border-slate-200"
              }`}
            >
              {s}
            </div>
            {i < STAGES.length - 1 && (
              <div className={`w-3 h-px ${active ? "bg-emerald-300" : "bg-slate-200"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}
