import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

type ToastKind = "success" | "error" | "info";
interface ToastMsg {
  id: number;
  kind: ToastKind;
  text: string;
}

interface ToastApi {
  success: (text: string) => void;
  error: (text: string) => void;
  info: (text: string) => void;
}

const ToastCtx = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const v = useContext(ToastCtx);
  if (!v) throw new Error("useToast outside <ToastProvider>");
  return v;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastMsg[]>([]);
  const push = useCallback((kind: ToastKind, text: string) => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, kind, text }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), 4000);
  }, []);
  const api: ToastApi = {
    success: (t) => push("success", t),
    error: (t) => push("error", t),
    info: (t) => push("info", t),
  };
  return (
    <ToastCtx.Provider value={api}>
      {children}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 max-w-sm">
        {items.map((t) => (
          <ToastCard key={t.id} t={t} onClose={() => setItems((x) => x.filter((i) => i.id !== t.id))} />
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

function ToastCard({ t, onClose }: { t: ToastMsg; onClose: () => void }) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const id = window.setTimeout(() => setShow(true), 10);
    return () => window.clearTimeout(id);
  }, []);
  const palette =
    t.kind === "success"
      ? "border-emerald-200 bg-white text-emerald-900 ring-1 ring-emerald-100"
      : t.kind === "error"
      ? "border-rose-200 bg-white text-rose-900 ring-1 ring-rose-100"
      : "border-blue-200 bg-white text-blue-900 ring-1 ring-blue-100";
  const iconPalette =
    t.kind === "success" ? "bg-emerald-500" : t.kind === "error" ? "bg-rose-500" : "bg-blue-500";
  const icon = t.kind === "success" ? "✓" : t.kind === "error" ? "✕" : "ℹ";
  return (
    <div
      className={`flex items-start gap-3 px-4 py-3 rounded-lg border shadow-lg shadow-slate-900/5 transition-all duration-200 ${palette} ${
        show ? "opacity-100 translate-x-0" : "opacity-0 translate-x-4"
      }`}
    >
      <span
        className={`w-5 h-5 rounded-full grid place-items-center text-white text-xs font-bold ${iconPalette} mt-px`}
      >
        {icon}
      </span>
      <span className="flex-1 text-sm leading-snug">{t.text}</span>
      <button onClick={onClose} className="text-slate-400 hover:text-slate-700 leading-none">
        ✕
      </button>
    </div>
  );
}
