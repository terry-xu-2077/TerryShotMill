import { useEffect, useState } from "react";
import type { DeletionImpact, LifecycleAction, LifecycleGateway } from "../../gateways/lifecycleGateway";
import { Button, Checkbox } from "../../ui/primitives";
import { Dialog } from "../../ui/overlay";
import "./TaskLifecycle.css";

export type TaskLifecycleIntent = {
  action: LifecycleAction | "purge";
  tasks: { id: string; title: string }[];
};

const labels = {
  archive: "归档任务", unarchive: "取消归档", trash: "删除任务",
  restore: "恢复任务", purge: "永久删除任务",
};
const relationships: Record<string, string> = {
  visual: "画面承接", semantic: "提示词上下文", audio: "音频承接",
  latent: "生成承接", native: "生成承接", fallback: "画面承接",
};

export function TaskLifecycleDialog({ projectId, intent, gateway, onClose, onChanged }: {
  projectId: string; intent: TaskLifecycleIntent; gateway: LifecycleGateway;
  onClose: () => void; onChanged: () => Promise<void>;
}) {
  const [impacts, setImpacts] = useState<DeletionImpact[]>([]);
  const [loading, setLoading] = useState(intent.action === "trash" || intent.action === "purge");
  const [previewError, setPreviewError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [committed, setCommitted] = useState(false);
  const [archiveResults, setArchiveResults] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const destructive = intent.action === "trash" || intent.action === "purge";
  useEffect(() => {
    if (!destructive) return;
    let cancelled = false;
    setLoading(true);
    setPreviewError("");
    gateway.deletionPreview(projectId, intent.tasks.map(task => task.id)).then(items => {
      if (!cancelled) setImpacts(items);
    }).catch(reason => {
      if (!cancelled) setPreviewError(reason instanceof Error ? reason.message : "无法检查受影响任务");
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectId, intent, gateway, destructive, attempt]);

  const submit = async () => {
    if (busy || loading || previewError) return;
    setBusy(true); setError("");
    let saved = committed;
    try {
      if (!saved) {
        const ids = intent.tasks.map(task => task.id);
        if (intent.action === "purge") await gateway.purgeTasks(projectId, ids, archiveResults);
        else await gateway.transitionTasks(projectId, ids, intent.action);
        saved = true; setCommitted(true);
      }
      await onChanged();
      onClose();
    } catch (reason) {
      setError(saved ? "操作已完成，但列表刷新失败。请重试刷新。"
        : reason instanceof Error ? reason.message : "操作未完成，请重试。");
    } finally { setBusy(false); }
  };

  return <Dialog open icon={destructive ? "delete" : "history"} title={labels[intent.action]}
    onClose={() => { if (!busy) onClose(); }}>
    <div className="task-lifecycle-dialog">
      <p className="task-lifecycle-copy">{labels[intent.action]}：{intent.tasks.length} 项</p>
      <ul className="task-lifecycle-list" aria-label="所选任务">
        {intent.tasks.map(task => <li key={task.id}>{task.title}</li>)}
      </ul>
      {intent.action === "trash" && <p className="task-lifecycle-copy">任务及全部生成结果移入回收站，可恢复。</p>}
      {intent.action === "archive" && <p className="task-lifecycle-copy">归档后可查看结果；编辑或生成前需取消归档。</p>}
      {intent.action === "purge" && <>
        <p className="task-lifecycle-copy">永久删除后无法恢复任务。</p>
        <label className="task-lifecycle-option"><Checkbox checked={archiveResults} disabled={busy || committed}
          onChange={setArchiveResults} ariaLabel="归档全部生成结果后删除" />归档全部生成结果后删除</label>
        <p className="task-lifecycle-copy">{archiveResults ? "保留的结果可在首页“生成结果归档”中找到。"
          : "未归档的全部生成结果也将删除，无法恢复。"}</p>
      </>}
      {loading && <p role="status">正在检查受影响任务…</p>}
      {previewError && <div role="alert">{previewError}<Button onClick={() => setAttempt(value => value + 1)}>重试检查</Button></div>}
      {!loading && !previewError && impacts.length > 0 && <section aria-label="受影响任务">
        <h3 className="task-lifecycle-impact-title">以下任务使用了所选任务的结果</h3>
        <ul className="task-lifecycle-list">{impacts.map((impact, index) => <li key={`${impact.targetTaskId}-${index}`}>
          {impact.targetTaskTitle}：{relationships[impact.kind] ?? "上下文承接"}来源“{impact.sourceTaskTitle}”
          {intent.action === "purge" ? "将永久丢失，已有生成结果不变。" : "将移入回收站，已有生成结果保留。"}
        </li>)}</ul>
      </section>}
      {error && <p role="alert">{error}</p>}
      <footer className="task-lifecycle-actions">
        <Button disabled={busy} onClick={onClose}>取消</Button>
        <Button variant="accent" disabled={busy || loading || !!previewError || !intent.tasks.length}
          onClick={() => void submit()}>{busy ? "处理中…" : committed ? "重试刷新" : labels[intent.action]}</Button>
      </footer>
    </div>
  </Dialog>;
}
