import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, wsUrl } from "../lib/api";
import type { Incident } from "../lib/types";
import { SeverityBadge } from "../components/SeverityBadge";
import { StateStepper } from "../components/StateStepper";
import { Sparkline } from "../components/Sparkline";
import { useFilters } from "../store/filters";
import { useToast } from "../components/Toast";
import { relTime } from "../lib/format";

function StatCard({
  label,
  value,
  accent,
  hint,
}: {
  label: string;
  value: string | number;
  accent?: string;
  hint?: string;
}) {
  return (
    <div className="card p-4">
      <div className="text-[10px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${accent ?? "text-slate-900"}`}>{value}</div>
      {hint && <div className="text-[11px] text-slate-500 mt-1">{hint}</div>}
    </div>
  );
}

export default function LiveFeed() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();
  const [_, setTick] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const [focused, setFocused] = useState(0);
  const filters = useFilters();

  const { data: incidents = [], isLoading } = useQuery<Incident[]>({
    queryKey: ["incidents"],
    queryFn: () => api.get<Incident[]>("/incidents?limit=200"),
    refetchInterval: 4_000,
  });

  useEffect(() => {
    const ws = new WebSocket(wsUrl("/ws/dashboard"));
    wsRef.current = ws;
    ws.onmessage = () => qc.invalidateQueries({ queryKey: ["incidents"] });
    return () => ws.close();
  }, [qc]);

  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), 5_000);
    return () => clearInterval(t);
  }, []);

  const filtered = useMemo(() => {
    const search = filters.search.trim().toLowerCase();
    return incidents.filter((i) => {
      if (i.state !== "CLOSED" && !filters.states.has(i.state)) return false;
      if (!filters.severities.has(i.severity)) return false;
      if (search && !i.component_id.toLowerCase().includes(search) && !i.title.toLowerCase().includes(search))
        return false;
      return true;
    });
  }, [incidents, filters]);

  const active = filtered.filter((i) => i.state !== "CLOSED");
  const closed = filtered.filter((i) => i.state === "CLOSED");

  const grouped = useMemo(() => {
    if (filters.groupBy === "none") return [{ key: "All active", items: active }];
    const map: Record<string, Incident[]> = {};
    for (const i of active) {
      const key = filters.groupBy === "severity" ? i.severity : i.component_id;
      (map[key] = map[key] || []).push(i);
    }
    const order = filters.groupBy === "severity" ? ["P0", "P1", "P2", "P3"] : Object.keys(map).sort();
    return order.filter((k) => map[k]?.length).map((k) => ({ key: k, items: map[k] }));
  }, [active, filters.groupBy]);

  const totals = useMemo(
    () => ({
      active: incidents.filter((i) => i.state !== "CLOSED").length,
      p0: incidents.filter((i) => i.state !== "CLOSED" && i.severity === "P0").length,
      closed: incidents.filter((i) => i.state === "CLOSED").length,
      signals: incidents.reduce((acc, i) => acc + (i.signal_count || 0), 0),
    }),
    [incidents],
  );

  const components = useMemo(() => {
    const map: Record<string, { count: number; sev: string }> = {};
    for (const i of incidents.filter((x) => x.state !== "CLOSED")) {
      if (!map[i.component_id] || severityRank(i.severity) < severityRank(map[i.component_id].sev as any))
        map[i.component_id] = { count: i.signal_count, sev: i.severity };
    }
    return Object.entries(map);
  }, [incidents]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "j") {
        e.preventDefault();
        setFocused((i) => Math.min(i + 1, active.length - 1));
      } else if (e.key === "k") {
        e.preventDefault();
        setFocused((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter" && active[focused]) {
        nav(`/incidents/${active[focused].id}`);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, focused, nav]);

  const summarize = useMutation({
    mutationFn: (id: string) => api.post<any>(`/incidents/${id}/summarize`, {}),
    onSuccess: () => {
      toast.success("AI summary generated");
      qc.invalidateQueries({ queryKey: ["incidents"] });
    },
    onError: (e: any) => toast.error(`Summary failed: ${e?.body || e?.message || "unknown"}`),
  });

  return (
    <div className="space-y-6 max-w-[1100px] mx-auto">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Live feed</h1>
        <p className="text-sm text-slate-500 mt-1">
          {filtered.length === incidents.length ? "All incidents." : `Filtered: ${filtered.length} of ${incidents.length}`}
          {" "}· Sorted by severity, then recency.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Active" value={totals.active} accent={totals.active ? "text-rose-600" : "text-emerald-600"} />
        <StatCard label="P0" value={totals.p0} accent={totals.p0 ? "text-rose-600" : "text-slate-900"} hint="critical" />
        <StatCard label="Closed" value={totals.closed} accent="text-emerald-600" />
        <StatCard label="Signals" value={totals.signals.toLocaleString()} hint="all time" />
      </div>

      {components.length > 0 && (
        <div className="card p-4">
          <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-3 font-semibold">
            Components affected
          </div>
          <div className="flex flex-wrap gap-2">
            {components.map(([cid, { count, sev }]) => (
              <button
                key={cid}
                onClick={() => filters.setSearch(cid)}
                className="pill border-slate-200 bg-white hover:bg-slate-50 transition text-slate-700"
              >
                <span className={`w-1.5 h-1.5 rounded-full ${SEV_DOT[sev as any] || "bg-slate-400"}`} />
                <span className="font-mono">{cid}</span>
                <span className="text-slate-500 font-mono">· {count.toLocaleString()}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {isLoading && <div className="text-sm text-slate-500">Loading…</div>}

      {!isLoading && incidents.length === 0 && (
        <div className="card p-12 text-center">
          <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-emerald-50 grid place-items-center text-emerald-600 text-xl">
            ✓
          </div>
          <h2 className="font-semibold text-lg text-slate-900">All clear</h2>
          <p className="text-sm text-slate-500 mt-2 max-w-md mx-auto">
            No active incidents. Run{" "}
            <code className="font-mono text-blue-700 bg-blue-50 px-2 py-0.5 rounded">python scripts/simulate_failure.py</code>{" "}
            to generate one.
          </p>
        </div>
      )}

      {!isLoading && incidents.length > 0 && active.length === 0 && filtered.length < incidents.length && (
        <div className="card p-8 text-center text-sm text-slate-500">
          No active incidents match these filters.
          <button onClick={filters.resetAll} className="ml-2 text-blue-600 hover:text-blue-700">
            Reset
          </button>
        </div>
      )}

      <div className="space-y-6">
        {grouped.map((group) => (
          <div key={group.key}>
            {filters.groupBy !== "none" && (
              <div className="text-xs uppercase tracking-widest text-slate-500 mb-2 font-semibold">
                {group.key} <span className="text-slate-400 font-normal">({group.items.length})</span>
              </div>
            )}
            <div className="grid gap-3">
              {group.items.map((inc) => {
                const idxInActive = active.indexOf(inc);
                const isFocused = idxInActive === focused;
                return (
                  <Link to={`/incidents/${inc.id}`} key={inc.id} className="block group">
                    <div
                      className={`card p-5 transition-all ${
                        inc.severity === "P0" ? "border-l-4 border-l-rose-500" : ""
                      } ${
                        isFocused
                          ? "border-blue-500 ring-2 ring-blue-500/20 shadow-md"
                          : "hover:border-blue-300 hover:shadow-md"
                      }`}
                    >
                      <div className="flex items-start gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap mb-2">
                            <SeverityBadge sev={inc.severity} />
                            <span className="text-sm font-mono text-slate-700">{inc.component_id}</span>
                            <span className="pill border-slate-200 bg-slate-50 text-slate-600">{inc.component_kind}</span>
                            <StateStepper state={inc.state} />
                          </div>
                          <div className="font-medium text-slate-900 group-hover:text-blue-700 text-base">
                            {inc.title}
                          </div>
                          {inc.summary ? (
                            <p className="text-sm text-slate-600 mt-2 leading-relaxed">
                              <span className="text-blue-600 mr-1.5">✨</span>
                              {inc.summary}
                            </p>
                          ) : (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.preventDefault();
                                summarize.mutate(inc.id);
                              }}
                              className="text-xs text-blue-600 hover:text-blue-700 mt-2 inline-flex items-center gap-1 hover:underline"
                            >
                              ✨ Generate AI summary {summarize.isPending && summarize.variables === inc.id ? "…" : ""}
                            </button>
                          )}

                          <div className="mt-3">
                            <Sparkline incidentId={inc.id} />
                          </div>
                        </div>
                        <div className="text-right text-xs text-slate-500 space-y-0.5 shrink-0 min-w-[140px]">
                          <div className="font-mono text-slate-900 text-xl font-semibold">
                            {inc.signal_count.toLocaleString()}
                          </div>
                          <div className="text-[11px] uppercase tracking-widest">signals</div>
                          <div className="pt-2">started {relTime(inc.first_signal_at)}</div>
                          <div>last {relTime(inc.last_signal_at)}</div>
                        </div>
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {closed.length > 0 && (
        <details className="mt-6">
          <summary className="text-sm text-slate-500 cursor-pointer select-none hover:text-slate-700 transition">
            Closed ({closed.length})
          </summary>
          <div className="mt-3 grid gap-2">
            {closed.map((inc) => (
              <Link to={`/incidents/${inc.id}`} key={inc.id}>
                <div className="card p-3 text-sm flex items-center gap-3 hover:border-blue-300">
                  <SeverityBadge sev={inc.severity} />
                  <span className="font-mono text-slate-500 text-xs">{inc.component_id}</span>
                  <span className="text-slate-700 truncate">{inc.title}</span>
                  <span className="ml-auto text-xs text-slate-500 whitespace-nowrap">
                    MTTR {inc.mttr_seconds != null ? `${Math.round(inc.mttr_seconds / 60)}m` : "—"}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

const SEV_DOT: Record<string, string> = {
  P0: "bg-rose-500",
  P1: "bg-orange-500",
  P2: "bg-amber-500",
  P3: "bg-blue-500",
};

function severityRank(s: string): number {
  return ({ P0: 0, P1: 1, P2: 2, P3: 3 } as Record<string, number>)[s] ?? 99;
}
