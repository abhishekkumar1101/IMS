import { useQuery } from "@tanstack/react-query";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../lib/api";

interface Point {
  t: string;
  signals: number;
  anomalies: number;
}

export function SignalFlowChart({ incidentId }: { incidentId: string }) {
  const { data = [] } = useQuery<Point[]>({
    queryKey: ["timeseries", incidentId],
    queryFn: () => api.get<Point[]>(`/incidents/${incidentId}/timeseries?minutes=30`),
    refetchInterval: 5_000,
  });

  if (!data.length) {
    return (
      <div className="h-44 grid place-items-center text-xs text-slate-500">
        No timeseries data yet — run the simulator.
      </div>
    );
  }
  const formatted = data.map((p) => ({
    ...p,
    label: new Date(p.t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
  }));

  return (
    <div className="h-44 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={formatted} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
          <defs>
            <linearGradient id="signals" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#2563eb" stopOpacity={0.5} />
              <stop offset="100%" stopColor="#2563eb" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis dataKey="label" stroke="#94a3b8" fontSize={10} tickLine={false} axisLine={false} />
          <YAxis stroke="#94a3b8" fontSize={10} tickLine={false} axisLine={false} />
          <Tooltip
            contentStyle={{
              background: "#ffffff",
              border: "1px solid #e2e8f0",
              borderRadius: 8,
              fontSize: 12,
              boxShadow: "0 4px 6px -1px rgba(0,0,0,0.08)",
            }}
            labelStyle={{ color: "#475569" }}
          />
          <Area type="monotone" dataKey="signals" stroke="#2563eb" strokeWidth={2} fill="url(#signals)" />
          <Line type="monotone" dataKey="anomalies" stroke="#c026d3" strokeWidth={2} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
