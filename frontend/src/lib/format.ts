export function relTime(iso: string): string {
  const d = new Date(iso).getTime();
  const diff = (Date.now() - d) / 1000;
  if (diff < 5) return "just now";
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

export function humanDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m ${seconds % 60}s`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  const d = Math.floor(h / 24);
  return `${d}d ${h % 24}h`;
}

export function nicknameFromStorage(): string {
  let nick = localStorage.getItem("ims:nick");
  if (!nick) {
    const adjectives = ["calm", "swift", "brave", "lucid", "quiet", "sharp", "vivid", "bold"];
    const animals = ["fox", "owl", "hawk", "wolf", "lynx", "otter", "raven", "ibex"];
    nick = `${adjectives[Math.floor(Math.random() * adjectives.length)]}-${animals[Math.floor(Math.random() * animals.length)]}-${Math.floor(Math.random() * 100)}`;
    localStorage.setItem("ims:nick", nick);
  }
  return nick;
}
