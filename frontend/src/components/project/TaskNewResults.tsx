import { useCallback, useState } from "react";

type Kind = "video" | "prompt";
export type NewResults = Partial<Record<Kind, string | null>>;
const key = "shotmill.viewed-results.v1";
function read(): Record<string, true> {
  try { return JSON.parse(localStorage.getItem(key) ?? "{}"); } catch { return {}; }
}

export function useViewedResults() {
  const [viewed, setViewed] = useState(read);
  const markViewed = useCallback((kind: Kind, id: string) => {
    setViewed(current => {
      const token = `${kind}:${id}`;
      if (current[token]) return current;
      const next = { ...current, [token]: true as const };
      try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* Session state still works. */ }
      return next;
    });
  }, []);
  return { markViewed, unread: (results?: NewResults) =>
    (Object.entries(results ?? {}) as [Kind, string | null][])
      .filter(([kind, id]) => id && !viewed[`${kind}:${id}`]).map(([kind]) => kind) };
}

export function TaskNewResults({ kinds }: { kinds: Kind[] }) {
  if (!kinds.length) return null;
  return <span className="task-new-results">{kinds.map(kind =>
    <span key={kind} className={`task-new-sticker is-${kind}`} role="img"
      aria-label={kind === "video" ? "新视频结果" : "新提示词增强结果"}>
      <span className="task-new-sticker-word">新</span>
    </span>)}</span>;
}
