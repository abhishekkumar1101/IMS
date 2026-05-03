import { useState } from "react";
import { api } from "../lib/api";
import { nicknameFromStorage } from "../lib/format";

const ROOT_CAUSE_CATEGORIES = [
  "configuration drift",
  "deployment regression",
  "infrastructure failure",
  "capacity / saturation",
  "third-party outage",
  "data corruption",
  "code defect",
  "human error",
  "security incident",
  "other",
];

export function RCAForm({
  incidentId,
  firstSignalAt,
  onClose,
  onSubmitted,
}: {
  incidentId: string;
  firstSignalAt: string;
  onClose: () => void;
  onSubmitted: () => void;
}) {
  const [start, setStart] = useState(toLocalInput(firstSignalAt));
  const [end, setEnd] = useState(toLocalInput(new Date().toISOString()));
  const [category, setCategory] = useState(ROOT_CAUSE_CATEGORIES[0]);
  const [fix, setFix] = useState("");
  const [prevention, setPrevention] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);
    try {
      await api.post<any>(`/incidents/${incidentId}/rca`, {
        root_cause_category: category,
        fix_applied: fix.trim(),
        prevention_steps: prevention.trim(),
        start_time: new Date(start).toISOString(),
        end_time: new Date(end).toISOString(),
        submitted_by: nicknameFromStorage(),
      });
      onSubmitted();
    } catch (e: any) {
      setErr(e?.body || e?.message || "submission failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-30 bg-slate-900/40 backdrop-blur-sm grid place-items-center p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <form
        onSubmit={onSubmit}
        className="bg-white border border-slate-200 rounded-xl shadow-xl max-w-2xl w-full p-6 space-y-4 max-h-[90vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Submit RCA & close incident</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              A complete RCA is mandatory to close. MTTR is computed automatically.
            </p>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-700 text-xl leading-none">
            ✕
          </button>
        </div>

        <div className="grid sm:grid-cols-2 gap-3">
          <Field label="Incident start (first signal)">
            <input
              type="datetime-local"
              required
              className="input"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </Field>
          <Field label="Incident end (RCA submission)">
            <input type="datetime-local" required className="input" value={end} onChange={(e) => setEnd(e.target.value)} />
          </Field>
        </div>

        <Field label="Root cause category">
          <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
            {ROOT_CAUSE_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Fix applied" hint="What you did to resolve. Min 10 chars.">
          <textarea
            required
            minLength={10}
            rows={3}
            className="input resize-y"
            value={fix}
            onChange={(e) => setFix(e.target.value)}
            placeholder="Restored cache cluster, failed over to standby replica, etc."
          />
        </Field>

        <Field label="Prevention steps" hint="What will keep it from recurring. Min 10 chars.">
          <textarea
            required
            minLength={10}
            rows={3}
            className="input resize-y"
            value={prevention}
            onChange={(e) => setPrevention(e.target.value)}
            placeholder="Add canary deploy gate, alarm threshold, runbook link, etc."
          />
        </Field>

        {err && (
          <div className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-md p-3 font-mono whitespace-pre-wrap">
            {err}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? "Closing…" : "Close incident with RCA"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium text-slate-700 uppercase tracking-wide">{label}</span>
        {hint && <span className="text-xs text-slate-500">{hint}</span>}
      </div>
      {children}
    </label>
  );
}

function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const tz = d.getTimezoneOffset() * 60_000;
  return new Date(d.getTime() - tz).toISOString().slice(0, 16);
}
