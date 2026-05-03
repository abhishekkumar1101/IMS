import type { RawSignal } from "../lib/types";
import { relTime } from "../lib/format";

export function SignalsTable({ signals }: { signals: RawSignal[] }) {
  if (!signals.length) {
    return <div className="text-sm text-slate-500 p-6 text-center">No raw signals yet.</div>;
  }
  return (
    <div className="overflow-auto rounded-lg border border-slate-200 max-h-[480px]">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-xs text-slate-500 sticky top-0 border-b border-slate-200">
          <tr>
            <th className="text-left px-3 py-2 font-medium uppercase tracking-wide">When</th>
            <th className="text-left px-3 py-2 font-medium uppercase tracking-wide">Sev</th>
            <th className="text-left px-3 py-2 font-medium uppercase tracking-wide">Message</th>
            <th className="text-right px-3 py-2 font-medium uppercase tracking-wide">Latency</th>
            <th className="text-right px-3 py-2 font-medium uppercase tracking-wide">Anomaly</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s, i) => (
            <tr key={i} className="border-t border-slate-100 hover:bg-slate-50/70">
              <td className="px-3 py-2 text-slate-500 whitespace-nowrap">
                {relTime(s.created_at || s.occurred_at || new Date().toISOString())}
              </td>
              <td className="px-3 py-2 font-mono text-xs text-slate-700">{s.severity}</td>
              <td className="px-3 py-2 text-slate-800">{s.message}</td>
              <td className="px-3 py-2 text-right font-mono text-xs text-slate-500">
                {(s as any).latency_ms ? `${Math.round((s as any).latency_ms)}ms` : "—"}
              </td>
              <td className="px-3 py-2 text-right">
                {s.is_anomalous ? (
                  <span className="pill bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200">anomaly</span>
                ) : s.anomaly_score != null ? (
                  <span className="text-xs text-slate-500 font-mono">{s.anomaly_score.toFixed(3)}</span>
                ) : (
                  <span className="text-xs text-slate-300">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
