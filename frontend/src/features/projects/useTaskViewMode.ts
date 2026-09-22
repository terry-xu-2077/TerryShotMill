import { useState } from "react";

type TaskViewMode = "list" | "card";
const key = (projectId: string) => `shotmill.task-view.${projectId}`;
function read(projectId: string): TaskViewMode {
  try { return localStorage.getItem(key(projectId)) === "card" ? "card" : "list"; }
  catch { return "list"; }
}

export function useTaskViewMode(projectId: string) {
  const [views, setViews] = useState<Record<string, TaskViewMode>>({});
  const mode = views[projectId] ?? read(projectId);
  function setMode(next: TaskViewMode) {
    setViews(current => ({ ...current, [projectId]: next }));
    try { localStorage.setItem(key(projectId), next); } catch { /* Keep this session usable. */ }
  }
  return [mode, setMode] as const;
}
