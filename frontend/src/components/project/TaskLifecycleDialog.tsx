import { useEffect, useState } from "react";
import type { DeletionImpact, LifecycleGateway } from "../../gateways/lifecycleGateway";
import { Button } from "../../ui/primitives";
import { Dialog } from "../../ui/overlay";
import "./TaskLifecycle.css";

export type TaskLifecycleIntent = { tasks: { id: string; title: string }[] };

const relationships: Record<string, string> = {
  visual: "画面承接", semantic: "提示词上下文", audio: "音频承接",
  latent: "生成承接", native: "生成承接", fallback: "画面承接",
};

export function TaskLifecycleDialog({ projectId, intent, gateway, onClose, onChanged }: {
  projectId: string; intent: TaskLifecycleIntent; gateway: LifecycleGateway;
  onClose: () => void; onChanged: () => Promise<void>;
}) {
  const [impacts, setImpacts] = useState<DeletionImpact[]>([]);
  const [loading, setLoading] = useState(true);
  const [previewError, setPreviewError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [committed, setCommitted] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setPreviewError("");
    gateway.deletionPreview(projectId, intent.tasks.map(task => task.id)).then(items => {
      if (!cancelled) setImpacts(items);
    }).catch(reason => {
      if (!cancelled) setPreviewError(reason instanceof Error ? reason.message : "无法检查受影响任务");
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectId, intent, gateway, attempt]);

  const submit = async () => {
    if (busy || loading || previewError) return;
    setBusy(true); setError("");
    let saved = committed;
    try {
      if (!saved) {
        await gateway.deleteTasks(projectId, intent.tasks.map(task => task.id));
        saved = true; setCommitted(true);
      }
      await onChanged();
      onClose();
    } catch (reason) {
      setError(saved ? "删除已完成，但列表刷新失败。请重试刷新。"
        : reason instanceof Error ? reason.message : "删除未完成，请重试。");
    } finally { setBusy(false); }
  };

  return <Dialog open icon="delete" title="删除任务" onClose={() => { if (!busy) onClose(); }}>
    <div className="task-lifecycle-dialog">
      <p className="task-lifecycle-copy">确定删除以下 {intent.tasks.length} 个任务吗？任务及其生成结果将被删除，无法恢复；本机导入的原始素材不会删除。</p>
      <ul className="task-lifecycle-list" aria-label="所选任务">
        {intent.tasks.map(task => <li key={task.id}>{task.title}</li>)}
      </ul>
      {loading && <p role="status">正在检查受影响任务…</p>}
      {previewError && <div role="alert">{previewError}<Button onClick={() => setAttempt(value => value + 1)}>重试检查</Button></div>}
      {!loading && !previewError && impacts.length > 0 && <section aria-label="受影响任务">
        <h3 className="task-lifecycle-impact-title">以下任务仍引用所选任务的结果</h3>
        <ul className="task-lifecycle-list">{impacts.map((impact, index) => <li key={`${impact.targetTaskId}-${index}`}>
          {impact.targetTaskTitle}：{relationships[impact.kind] ?? "上下文承接"}来源“{impact.sourceTaskTitle}”将失效，已有生成结果不变。
        </li>)}</ul>
      </section>}
      {error && <p role="alert">{error}</p>}
      <footer className="task-lifecycle-actions">
        <Button disabled={busy} onClick={onClose}>取消</Button>
        <Button variant="accent" disabled={busy || loading || !!previewError || !intent.tasks.length}
          onClick={() => void submit()}>{busy ? "删除中…" : committed ? "重试刷新" : "确认删除"}</Button>
      </footer>
    </div>
  </Dialog>;
}
