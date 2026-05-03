import { useEffect, useRef } from "react";
import { useFilters } from "../store/filters";
import type { IncidentState, Severity } from "../lib/types";

const SEVERITIES: Severity[] = ["P0", "P1", "P2", "P3"];
const STATES: IncidentState[] = ["OPEN", "INVESTIGATING", "RESOLVED"];

const SEV_DOT: Record<Severity, string> = {
  P0: "bg-rose-500",
  P1: "bg-orange-500",
  P2: "bg-amber-500",
  P3: "bg-blue-500",
};

const STATE_LABEL: Record<IncidentState, string> = {
  OPEN: "Open",
  INVESTIGATING: "Investigating",
  RESOLVED: "Resolved",
  CLOSED: "Closed",
};

export function Sidebar() {
  const f = useFilters();
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "/") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <aside className="w-64 shrink-0 border-r border-slate-200 bg-white flex flex-col h-[calc(100vh-57px)] sticky top-[57px]">
      <div className="p-5 space-y-6 overflow-y-auto flex-1">
        <div>
          <Label>Search</Label>
          <input
            ref={searchRef}
            className="input mt-2"
            placeholder="component id…  ( / )"
            value={f.search}
            onChange={(e) => f.setSearch(e.target.value)}
          />
        </div>

        <div>
          <Label>Severity</Label>
          <div className="space-y-1.5 mt-2">
            {SEVERITIES.map((s) => (
              <FilterRow
                key={s}
                checked={f.severities.has(s)}
                onChange={() => f.toggleSeverity(s)}
                label={s}
                dotClass={SEV_DOT[s]}
              />
            ))}
          </div>
        </div>

        <div>
          <Label>State</Label>
          <div className="space-y-1.5 mt-2">
            {STATES.map((s) => (
              <FilterRow
                key={s}
                checked={f.states.has(s)}
                onChange={() => f.toggleState(s)}
                label={STATE_LABEL[s]}
              />
            ))}
          </div>
        </div>

        <div>
          <Label>Group by</Label>
          <select
            className="input mt-2"
            value={f.groupBy}
            onChange={(e) => f.setGroupBy(e.target.value as any)}
          >
            <option value="none">None</option>
            <option value="severity">Severity</option>
            <option value="component">Component</option>
          </select>
        </div>

        <button onClick={f.resetAll} className="text-xs text-slate-500 hover:text-blue-600 transition">
          Reset filters
        </button>
      </div>

      <div className="border-t border-slate-200 p-4 text-xs text-slate-500 space-y-1 bg-slate-50">
        <div className="font-semibold text-slate-700 uppercase tracking-widest text-[10px]">Shortcuts</div>
        <div>
          <kbd className="kbd">/</kbd> search · <kbd className="kbd">?</kbd> help
        </div>
        <div>
          <kbd className="kbd">j</kbd>/<kbd className="kbd">k</kbd> navigate
        </div>
      </div>
    </aside>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">{children}</div>
  );
}

function FilterRow({
  checked,
  onChange,
  label,
  dotClass,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
  dotClass?: string;
}) {
  return (
    <label className="flex items-center gap-2 text-sm cursor-pointer text-slate-700 hover:text-slate-900">
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className="w-3.5 h-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-500/30 focus:ring-offset-0"
      />
      {dotClass && <span className={`w-2 h-2 rounded-full ${dotClass}`} />}
      <span>{label}</span>
    </label>
  );
}
