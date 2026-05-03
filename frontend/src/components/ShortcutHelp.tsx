import { useEffect, useState } from "react";

const SHORTCUTS: { key: string; desc: string }[] = [
  { key: "/", desc: "Focus search" },
  { key: "j / k", desc: "Navigate incidents" },
  { key: "Enter", desc: "Open focused incident" },
  { key: "i", desc: "Start investigating (on detail)" },
  { key: "r", desc: "Mark resolved (on detail)" },
  { key: "c", desc: "Focus comment box (on detail)" },
  { key: "g h", desc: "Go home (Live feed)" },
  { key: "?", desc: "Toggle this help" },
  { key: "Esc", desc: "Close modal" },
];

export function ShortcutHelp() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "?") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-sm grid place-items-center p-4"
      onClick={() => setOpen(false)}
    >
      <div
        className="bg-white border border-slate-200 rounded-xl shadow-xl max-w-md w-full p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-slate-900">Keyboard shortcuts</h2>
          <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-slate-700 text-xl leading-none">
            ✕
          </button>
        </div>
        <table className="w-full text-sm">
          <tbody>
            {SHORTCUTS.map((s) => (
              <tr key={s.key} className="border-t border-slate-100 first:border-t-0">
                <td className="py-2 pr-4 align-top">
                  <kbd className="kbd">{s.key}</kbd>
                </td>
                <td className="py-2 text-slate-700">{s.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
