import { create } from "zustand";
import type { IncidentState, Severity } from "../lib/types";

export type GroupBy = "severity" | "component" | "none";

interface FiltersState {
  severities: Set<Severity>;
  states: Set<IncidentState>;
  search: string;
  groupBy: GroupBy;
  toggleSeverity: (s: Severity) => void;
  toggleState: (s: IncidentState) => void;
  setSearch: (s: string) => void;
  setGroupBy: (g: GroupBy) => void;
  resetAll: () => void;
}

const ALL_SEV: Severity[] = ["P0", "P1", "P2", "P3"];
const ALL_STATE: IncidentState[] = ["OPEN", "INVESTIGATING", "RESOLVED"];

export const useFilters = create<FiltersState>((set) => ({
  severities: new Set(ALL_SEV),
  states: new Set(ALL_STATE),
  search: "",
  groupBy: "none",
  toggleSeverity: (s) =>
    set((st) => {
      const next = new Set(st.severities);
      next.has(s) ? next.delete(s) : next.add(s);
      return { severities: next };
    }),
  toggleState: (s) =>
    set((st) => {
      const next = new Set(st.states);
      next.has(s) ? next.delete(s) : next.add(s);
      return { states: next };
    }),
  setSearch: (s) => set({ search: s }),
  setGroupBy: (g) => set({ groupBy: g }),
  resetAll: () => set({ severities: new Set(ALL_SEV), states: new Set(ALL_STATE), search: "", groupBy: "none" }),
}));
