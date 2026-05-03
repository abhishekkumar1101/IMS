import type { Viewer } from "../lib/types";

export function PresenceAvatars({ viewers }: { viewers: Viewer[] }) {
  if (!viewers.length) return null;
  return (
    <div className="flex items-center gap-2">
      <div className="flex -space-x-2">
        {viewers.slice(0, 5).map((v, i) => (
          <div
            key={`${v.nickname}-${i}`}
            title={v.nickname}
            className="w-7 h-7 rounded-full grid place-items-center text-[10px] font-bold text-white border-2 border-white shadow-sm"
            style={{ backgroundColor: v.avatar_color }}
          >
            {v.nickname.slice(0, 2).toUpperCase()}
          </div>
        ))}
      </div>
      <span className="text-xs text-slate-500">{viewers.length} viewing</span>
    </div>
  );
}
