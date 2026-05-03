const API_BASE = (import.meta.env.VITE_API_BASE as string) || "http://localhost:8000";
const WS_BASE = (import.meta.env.VITE_WS_BASE as string) || "ws://localhost:8000";

export async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text();
    throw Object.assign(new Error(text || res.statusText), { status: res.status, body: text });
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  get: <T>(p: string) => request<T>(p),
  post: <T>(p: string, body: unknown) => request<T>(p, { method: "POST", body: JSON.stringify(body) }),
};

export const wsUrl = (path: string) => `${WS_BASE}${path}`;
