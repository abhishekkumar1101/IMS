import { Outlet, Link, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "./lib/api";
import { useEffect, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { ShortcutHelp } from "./components/ShortcutHelp";

interface HealthResp {
  status: string;
  deps?: Record<string, string>;
  metrics?: { signals_per_sec_5s?: number; queue_depth?: number };
}

function StatusDot({ status }: { status: string }) {
  const color = status === "ok" ? "bg-emerald-500" : status === "degraded" ? "bg-amber-500" : "bg-rose-500";
  return <span className={`inline-block w-2 h-2 rounded-full ${color} pulse-soft`} />;
}

export default function App() {
  const loc = useLocation();
  const nav = useNavigate();
  const { data: health } = useQuery<HealthResp>({
    queryKey: ["health"],
    queryFn: () => api.get<HealthResp>("/health"),
    refetchInterval: 5_000,
  });

  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // Global shortcut: `g h` → go home.
  useEffect(() => {
    let g = false;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "g") {
        g = true;
        setTimeout(() => (g = false), 800);
      } else if (g && e.key === "h") {
        nav("/");
        g = false;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [nav]);

  const onDetail = loc.pathname.startsWith("/incidents/");

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white/90 backdrop-blur sticky top-0 z-20 shadow-sm">
        <div className="px-6 py-3 flex items-center gap-4">
          <Link to="/" className="flex items-center gap-2.5 group">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 grid place-items-center text-white font-bold shadow-sm">
              !
            </div>
            <div className="leading-tight">
              <div className="font-semibold tracking-tight text-slate-900">IMS</div>
              <div className="text-[10px] text-slate-500 uppercase tracking-widest">incident console</div>
            </div>
          </Link>
          <nav className="flex items-center gap-1 ml-4 text-sm">
            <Link
              to="/"
              className={`px-3 py-1.5 rounded-md transition ${
                loc.pathname === "/"
                  ? "bg-blue-50 text-blue-700"
                  : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
              }`}
            >
              Live feed
            </Link>
          </nav>
          <div className="ml-auto flex items-center gap-3 text-xs text-slate-600">
            <div className="hidden md:flex items-center gap-3 px-3 py-1.5 rounded-md bg-slate-50 border border-slate-200 font-mono">
              <span>
                <span className="text-slate-900 font-semibold">{health?.metrics?.signals_per_sec_5s ?? 0}</span>{" "}
                <span className="text-slate-500">sig/s</span>
              </span>
              <span className="text-slate-300">·</span>
              <span>
                <span className="text-slate-900 font-semibold">{health?.metrics?.queue_depth ?? 0}</span>{" "}
                <span className="text-slate-500">queue</span>
              </span>
            </div>
            <span className="hidden sm:inline font-mono text-slate-500">{now.toLocaleTimeString()}</span>
            <div className="flex items-center gap-2 px-2.5 py-1 rounded-md bg-slate-50 border border-slate-200">
              <StatusDot status={health?.status ?? "down"} />
              <span className="font-mono text-slate-700">{health?.status ?? "…"}</span>
            </div>
          </div>
        </div>
      </header>

      <div className="flex-1 flex">
        {!onDetail && <Sidebar />}
        <main className={`flex-1 px-6 py-6 ${onDetail ? "max-w-[1400px] mx-auto w-full" : ""}`}>
          <Outlet />
        </main>
      </div>

      <footer className="border-t border-slate-200 bg-white text-xs text-slate-500 py-2">
        <div className="px-6 flex flex-wrap items-center justify-between gap-2">
          <span>IMS — Mission-Critical Incident Management System</span>
          <span className="font-mono text-slate-400">MongoDB · Gemini 2.5 Flash Lite · Isolation Forest</span>
        </div>
      </footer>

      <ShortcutHelp />
    </div>
  );
}
