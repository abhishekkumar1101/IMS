import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, wsUrl } from "../lib/api";
import type { Comment, Incident, RawSignal, Viewer } from "../lib/types";
import { SeverityBadge } from "../components/SeverityBadge";
import { StateStepper } from "../components/StateStepper";
import { SignalsTable } from "../components/SignalsTable";
import { PresenceAvatars } from "../components/PresenceAvatars";
import { CommentsThread } from "../components/CommentsThread";
import { SignalFlowChart } from "../components/SignalFlowChart";
import { useToast } from "../components/Toast";
import { RCAForm } from "./RCAForm";
import { humanDuration, nicknameFromStorage, relTime } from "../lib/format";

type Tab = "signals" | "timeline" | "discussion" | "rca";

export default function IncidentDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();
  const wsRef = useRef<WebSocket | null>(null);
  const [viewers, setViewers] = useState<Viewer[]>([]);
  const [typing, setTyping] = useState<string | null>(null);
  const [showRCA, setShowRCA] = useState(false);
  const [tab, setTab] = useState<Tab>("signals");
  const commentRef = useRef<HTMLInputElement>(null);

  const { data: incident, isLoading, error } = useQuery({
    queryKey: ["incident", id],
    queryFn: () => api.get<Incident>(`/incidents/${id}`),
    refetchInterval: 4_000,
  });

  const { data: signals = [] } = useQuery({
    queryKey: ["signals", id],
    queryFn: () => api.get<RawSignal[]>(`/incidents/${id}/signals?limit=200`),
    refetchInterval: 5_000,
  });

  const { data: comments = [] } = useQuery({
    queryKey: ["comments", id],
    queryFn: () => api.get<Comment[]>(`/incidents/${id}/comments`),
  });

  const { data: rca } = useQuery({
    queryKey: ["rca", id],
    queryFn: () => api.get<any>(`/incidents/${id}/rca`).catch(() => null),
    enabled: !!incident?.has_rca,
  });

  const { data: timeline = [] } = useQuery({
    queryKey: ["timeline", id],
    queryFn: () =>
      api.get<{ t: string; signals: number; anomalies: number }[]>(`/incidents/${id}/timeseries?minutes=60`),
    refetchInterval: 6_000,
  });

  const transition = useMutation({
    mutationFn: (to_state: Incident["state"]) =>
      api.post<Incident>(`/incidents/${id}/transition`, { to_state, actor: nicknameFromStorage() }),
    onSuccess: (data) => {
      toast.success(`State → ${data.state}`);
      qc.invalidateQueries({ queryKey: ["incident", id] });
      qc.invalidateQueries({ queryKey: ["incidents"] });
    },
    onError: (e: any) => toast.error(`${prettyErr(e)}`),
  });

  const summarize = useMutation({
    mutationFn: () => api.post<any>(`/incidents/${id}/summarize`, {}),
    onSuccess: () => {
      toast.success("AI summary generated");
      qc.invalidateQueries({ queryKey: ["incident", id] });
    },
    onError: (e: any) => toast.error(`Summary failed: ${prettyErr(e)}`),
  });

  const postComment = useMutation({
    mutationFn: (body: string) =>
      api.post<Comment>(`/incidents/${id}/comments`, { author: nicknameFromStorage(), body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["comments", id] }),
    onError: (e: any) => toast.error(`Comment failed: ${prettyErr(e)}`),
  });

  useEffect(() => {
    if (!id) return;
    const nick = nicknameFromStorage();
    const ws = new WebSocket(wsUrl(`/ws/incidents/${id}`));
    wsRef.current = ws;
    ws.onopen = () => ws.send(JSON.stringify({ type: "hello", nickname: nick }));
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "presence") setViewers(msg.viewers as Viewer[]);
        else if (msg.type === "typing") {
          setTyping(msg.nickname);
          window.setTimeout(() => setTyping((t) => (t === msg.nickname ? null : t)), 2000);
        } else if (msg.type === "comment_added") {
          qc.invalidateQueries({ queryKey: ["comments", id] });
        }
      } catch {}
    };
    return () => ws.close();
  }, [id, qc]);

  useEffect(() => {
    if (!incident) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "i" && incident.state === "OPEN") {
        e.preventDefault();
        transition.mutate("INVESTIGATING");
      } else if (e.key === "r" && incident.state === "INVESTIGATING") {
        e.preventDefault();
        transition.mutate("RESOLVED");
      } else if (e.key === "c") {
        e.preventDefault();
        setTab("discussion");
        setTimeout(() => commentRef.current?.focus(), 50);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [incident, transition]);

  if (isLoading) return <div className="text-sm text-slate-500">Loading…</div>;
  if (error || !incident) {
    return (
      <div className="card p-8 text-center">
        <p className="text-rose-600">Could not load incident.</p>
        <Link to="/" className="btn mt-4 inline-flex">
          ← Back
        </Link>
      </div>
    );
  }

  const anomalousCount = signals.filter((s) => s.is_anomalous).length;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <button onClick={() => nav("/")} className="btn">
          ← Live feed
        </button>
        <PresenceAvatars viewers={viewers} />
      </div>

      <div className={`card p-6 ${incident.severity === "P0" ? "border-l-4 border-l-rose-500" : ""}`}>
        <div className="flex items-start gap-6 flex-wrap">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-3">
              <SeverityBadge sev={incident.severity} />
              <span className="font-mono text-sm text-slate-700">{incident.component_id}</span>
              <span className="pill border-slate-200 bg-slate-50 text-slate-600">{incident.component_kind}</span>
              <StateStepper state={incident.state} />
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{incident.title}</h1>
            {incident.summary ? (
              <p className="text-sm text-slate-600 mt-3 leading-relaxed max-w-3xl">
                <span className="text-blue-600 mr-1.5">✨</span>
                {incident.summary}
              </p>
            ) : (
              <button
                onClick={() => summarize.mutate()}
                disabled={summarize.isPending}
                className="text-xs text-blue-600 mt-3 hover:text-blue-700 inline-flex items-center gap-1 hover:underline disabled:opacity-50"
              >
                ✨ Generate AI summary {summarize.isPending ? "…" : ""}
              </button>
            )}
          </div>
          <div className="text-right text-xs text-slate-500 space-y-1 min-w-[150px]">
            <div className="font-mono text-slate-900 text-3xl font-semibold leading-none">
              {incident.signal_count.toLocaleString()}
            </div>
            <div className="text-[10px] uppercase tracking-widest">signals</div>
            <div className="pt-2 space-y-0.5">
              <div>started {relTime(incident.first_signal_at)}</div>
              <div>last {relTime(incident.last_signal_at)}</div>
              {anomalousCount > 0 && (
                <div className="pill bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200 mt-1">
                  {anomalousCount} anomalous
                </div>
              )}
            </div>
            {incident.mttr_seconds != null && (
              <div className="mt-2 pill bg-emerald-50 text-emerald-700 border-emerald-200">
                MTTR {humanDuration(incident.mttr_seconds)}
              </div>
            )}
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-2 pt-4 border-t border-slate-200">
          {incident.state === "OPEN" && (
            <button
              onClick={() => transition.mutate("INVESTIGATING")}
              disabled={transition.isPending}
              className="btn-primary"
            >
              {transition.isPending ? "…" : "Start investigating"} <kbd className="kbd ml-1 bg-blue-700 border-blue-500 text-white">i</kbd>
            </button>
          )}
          {incident.state === "INVESTIGATING" && (
            <button
              onClick={() => transition.mutate("RESOLVED")}
              disabled={transition.isPending}
              className="btn-primary"
            >
              {transition.isPending ? "…" : "Mark resolved"} <kbd className="kbd ml-1 bg-blue-700 border-blue-500 text-white">r</kbd>
            </button>
          )}
          {incident.state === "RESOLVED" && !incident.has_rca && (
            <button onClick={() => setShowRCA(true)} className="btn-primary">
              Submit RCA & close
            </button>
          )}
          {incident.state === "RESOLVED" && (
            <button
              onClick={() => transition.mutate("INVESTIGATING")}
              disabled={transition.isPending}
              className="btn"
            >
              Re-open
            </button>
          )}
          {incident.state === "CLOSED" && (
            <span className="pill bg-emerald-50 text-emerald-700 border-emerald-200">
              ✓ Closed with RCA
            </span>
          )}
        </div>
      </div>

      {timeline.length > 0 && (
        <section className="card p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-slate-900">Signal flow · last 60 min</h2>
            <div className="flex items-center gap-3 text-[11px] text-slate-500">
              <span className="inline-flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-blue-600" /> signals
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-fuchsia-600" /> anomalies
              </span>
            </div>
          </div>
          <SignalFlowChart incidentId={id} />
        </section>
      )}

      {showRCA && (
        <RCAForm
          incidentId={incident.id}
          firstSignalAt={incident.first_signal_at}
          onClose={() => setShowRCA(false)}
          onSubmitted={() => {
            setShowRCA(false);
            toast.success("Incident closed with RCA");
            qc.invalidateQueries({ queryKey: ["incident", id] });
            qc.invalidateQueries({ queryKey: ["incidents"] });
          }}
        />
      )}

      <section className="card overflow-hidden">
        <div className="flex border-b border-slate-200 px-2 bg-slate-50/50">
          <TabButton active={tab === "signals"} onClick={() => setTab("signals")}>
            Raw signals <span className="text-slate-400 ml-1">{signals.length}</span>
          </TabButton>
          <TabButton active={tab === "timeline"} onClick={() => setTab("timeline")}>
            Timeline
          </TabButton>
          <TabButton active={tab === "discussion"} onClick={() => setTab("discussion")}>
            Discussion <span className="text-slate-400 ml-1">{comments.length}</span>
          </TabButton>
          {incident.has_rca && (
            <TabButton active={tab === "rca"} onClick={() => setTab("rca")}>
              RCA
            </TabButton>
          )}
        </div>

        <div className="p-5">
          {tab === "signals" && <SignalsTable signals={signals} />}
          {tab === "timeline" && <Timeline incident={incident} signals={signals} />}
          {tab === "discussion" && (
            <CommentsThread
              comments={comments}
              typing={typing}
              onPost={async (body) => {
                await postComment.mutateAsync(body);
              }}
            />
          )}
          {tab === "rca" && rca && <RCAView rca={rca} mttr={incident.mttr_seconds || null} />}
        </div>
      </section>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button onClick={onClick} className={`tab ${active ? "tab-active" : ""}`}>
      {children}
    </button>
  );
}

function Timeline({ incident, signals }: { incident: Incident; signals: RawSignal[] }) {
  const items = [
    { ts: incident.first_signal_at, label: "First signal received", kind: "neutral" },
    { ts: incident.first_signal_at, label: `Work item created · ${incident.severity}`, kind: "create" },
    ...(signals[0]
      ? [{ ts: signals[0].created_at || signals[0].occurred_at || "", label: "Latest signal", kind: "signal" }]
      : []),
    ...(incident.state !== "OPEN" ? [{ ts: incident.last_signal_at, label: `State: ${incident.state}`, kind: "state" }] : []),
    ...(incident.closed_at
      ? [
          {
            ts: incident.closed_at,
            label: `Closed${incident.mttr_seconds ? ` · MTTR ${humanDuration(incident.mttr_seconds)}` : ""}`,
            kind: "closed",
          },
        ]
      : []),
  ];
  return (
    <ol className="relative pl-5 space-y-3">
      <span className="absolute left-1.5 top-2 bottom-2 w-px bg-slate-200" />
      {items.map((it, i) => (
        <li key={i} className="relative">
          <span
            className={`absolute -left-3.5 top-1.5 w-2 h-2 rounded-full ring-2 ring-white ${
              it.kind === "closed"
                ? "bg-emerald-500"
                : it.kind === "state"
                ? "bg-blue-500"
                : it.kind === "create"
                ? "bg-rose-500"
                : "bg-slate-400"
            }`}
          />
          <div className="text-sm text-slate-800">{it.label}</div>
          <div className="text-xs text-slate-500">{it.ts ? new Date(it.ts).toLocaleString() : "—"}</div>
        </li>
      ))}
    </ol>
  );
}

function RCAView({ rca, mttr }: { rca: any; mttr: number | null }) {
  return (
    <div className="space-y-4">
      <div className="grid sm:grid-cols-2 gap-4">
        <Field label="Root cause">{rca.root_cause_category}</Field>
        <Field label="Submitted">{new Date(rca.submitted_at).toLocaleString()}</Field>
        <Field label="Started">{new Date(rca.start_time).toLocaleString()}</Field>
        <Field label="Ended">{new Date(rca.end_time).toLocaleString()}</Field>
      </div>
      <Field label="Fix applied">{rca.fix_applied}</Field>
      <Field label="Prevention">{rca.prevention_steps}</Field>
      {mttr != null && (
        <div className="pill bg-emerald-50 text-emerald-700 border-emerald-200 inline-flex">
          MTTR {humanDuration(mttr)}
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1 font-semibold">{label}</div>
      <div className="text-sm text-slate-800 whitespace-pre-wrap">{children}</div>
    </div>
  );
}

function prettyErr(e: any): string {
  const body = e?.body || e?.message || "";
  try {
    const obj = JSON.parse(body);
    return obj?.detail || body;
  } catch {
    return body;
  }
}
