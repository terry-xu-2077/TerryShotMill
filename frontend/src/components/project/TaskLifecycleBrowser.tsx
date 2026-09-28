import { useCallback, useEffect, useState } from "react";
import type { LifecycleGateway } from "../../gateways/lifecycleGateway";
import type { TaskSummary } from "../../gateways/projectGateway";
import { Button, Checkbox, SegmentedControl } from "../../ui/primitives";
import { Dialog } from "../../ui/overlay";
import { TaskLifecycleDialog, type TaskLifecycleIntent } from "./TaskLifecycleDialog";
import { TaskRiskSticker } from "./TaskRiskSticker";
import { TaskReadOnlyDialog } from "./TaskReadOnlyDialog";
import "./TaskLifecycle.css";

export function TaskLifecycleBrowser({ projectId, gateway, onClose, onChanged, initialScope = "archived" }: {
  projectId: string; gateway: LifecycleGateway; onClose: () => void;
  onChanged: () => Promise<void>; initialScope?: "archived" | "trash";
}) {
  const [scope, setScope] = useState(initialScope);
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [intent, setIntent] = useState<TaskLifecycleIntent | null>(null);
  const [preview, setPreview] = useState<TaskSummary | null>(null);
  const [warnings, setWarnings] = useState<Record<string, string[]>>({});
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(""); setSelected(new Set()); setWarnings({}); setTasks([]);
    gateway.getWorkspace(projectId, scope).then(async workspace => {
      if (cancelled) return;
      setTasks(workspace.tasks);
      if (scope === "trash" && workspace.tasks.length) {
        const impacts = (await Promise.all(workspace.tasks.map(task =>
          gateway.deletionPreview(projectId, [task.id])))).flat();
        if (cancelled) return;
        const next: Record<string, string[]> = {};
        for (const impact of impacts) {
          (next[impact.sourceTaskId] ??= []).push(`“${impact.targetTaskTitle}”仍承接此任务的结果。永久删除后将丢失来源。`);
        }
        setWarnings(next);
      }
    }).catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "加载失败"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectId, gateway, scope, revision]);
  const changed = useCallback(async () => {
    await onChanged();
    setRevision(value => value + 1);
  }, [onChanged]);
  const chooseAction = (action: TaskLifecycleIntent["action"]) => {
    setIntent({ action, tasks: tasks.filter(task => selected.has(task.id)) });
  };
  return <>
    <Dialog open icon="history" title="任务归档与回收站" onClose={onClose}>
      <div className="task-lifecycle-browser">
        <SegmentedControl value={scope} ariaLabel="任务存放位置" options={[
          { value: "archived", label: "已归档" }, { value: "trash", label: "回收站" },
        ]} onChange={setScope} />
        {loading && <p role="status">正在加载…</p>}
        {error && <div role="alert">{error}<Button onClick={() => setRevision(value => value + 1)}>重试</Button></div>}
        {!loading && !error && !tasks.length && <p>这里没有任务。</p>}
        <div className="task-lifecycle-rows" aria-label={scope === "trash" ? "回收站任务" : "已归档任务"}>
          {tasks.map(task => <div className="task-lifecycle-row" key={task.id}>
            <Checkbox checked={selected.has(task.id)} ariaLabel={`选择任务 · ${task.title}`} onChange={checked => {
              setSelected(current => { const next = new Set(current); if (checked) next.add(task.id); else next.delete(task.id); return next; });
            }} />
            <span className="task-lifecycle-name">{task.title}</span>
            {!!warnings[task.id]?.length && <span className="task-lifecycle-warning"><TaskRiskSticker tooltipOnly warnings={warnings[task.id]} /></span>}
            <Button onClick={() => setPreview(task)}>查看任务</Button>
          </div>)}
        </div>
        <footer className="task-lifecycle-actions">
          <span>已选 {selected.size} 项</span>
          <Button disabled={!selected.size || loading || !!error} onClick={() => chooseAction(scope === "trash" ? "restore" : "unarchive")}>{scope === "trash" ? "恢复" : "取消归档"}</Button>
          <Button disabled={!selected.size || loading || !!error} onClick={() => chooseAction(scope === "trash" ? "purge" : "trash")}>{scope === "trash" ? "永久删除" : "删除"}</Button>
        </footer>
      </div>
    </Dialog>
    {intent && <TaskLifecycleDialog projectId={projectId} intent={intent} gateway={gateway}
      onClose={() => setIntent(null)} onChanged={changed} />}
    {preview && <TaskReadOnlyDialog projectId={projectId} taskId={preview.id} title={preview.title} onClose={() => setPreview(null)} />}
  </>;
}
