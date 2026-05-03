import { useState } from "react";
import type { Comment } from "../lib/types";
import { relTime, nicknameFromStorage } from "../lib/format";

export function CommentsThread({
  comments,
  onPost,
  typing,
}: {
  comments: Comment[];
  onPost: (body: string) => Promise<void>;
  typing: string | null;
}) {
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const me = nicknameFromStorage();

  return (
    <div className="space-y-3">
      <div className="space-y-2 max-h-96 overflow-auto pr-1">
        {comments.length === 0 && (
          <div className="text-sm text-slate-500 text-center py-6">No comments yet — start the discussion.</div>
        )}
        {comments.map((c) => (
          <div key={c.id} className="bg-slate-50 border border-slate-200 rounded-lg p-3">
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="font-semibold text-slate-800">{c.author}</span>
              <span className="text-slate-500">{relTime(c.created_at)}</span>
            </div>
            <p className="text-sm text-slate-800 whitespace-pre-wrap">{c.body}</p>
          </div>
        ))}
      </div>
      {typing && <div className="text-xs text-slate-500 italic">{typing} is typing…</div>}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (!body.trim() || busy) return;
          setBusy(true);
          try {
            await onPost(body.trim());
            setBody("");
          } finally {
            setBusy(false);
          }
        }}
        className="flex gap-2"
      >
        <input
          className="input flex-1"
          placeholder={`Comment as ${me}…`}
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <button type="submit" className="btn-primary" disabled={busy || !body.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
