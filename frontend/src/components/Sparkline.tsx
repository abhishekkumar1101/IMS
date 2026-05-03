import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

interface Point {
  t: string;
  n: number;
}

export function Sparkline({ incidentId, color = "#2563eb" }: { incidentId: string; color?: string }) {
  const { data = [] } = useQuery<Point[]>({
    queryKey: ["sparkline", incidentId],
    queryFn: () => api.get<Point[]>(`/incidents/${incidentId}/sparkline?minutes=10`),
    refetchInterval: 5_000,
  });

  if (data.length === 0) {
    return <div className="h-8 w-full bg-slate-100 rounded" />;
  }

  const W = 200;
  const H = 32;
  const max = Math.max(...data.map((d) => d.n), 1);
  const step = data.length > 1 ? W / (data.length - 1) : W;
  const points = data.map((d, i) => `${i * step},${H - (d.n / max) * (H - 4) - 2}`).join(" ");
  const fillPoints = `0,${H} ${points} ${(data.length - 1) * step},${H}`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-8 w-full" preserveAspectRatio="none">
      <polygon points={fillPoints} fill={color} fillOpacity={0.12} />
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
