import { FolderOpen, Sparkles, Film, ArrowUp, ArrowDown, Pause, Play, X } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "../../ui/primitives";
import type { ProjectRuntimeView, ProjectWorkspaceView, RuntimeTaskItem } from "../../gateways/projectGateway";
import { Dialog } from "../../ui/overlay";
import { formatElapsed } from "./taskTiming";

const stateLabels: Record<RuntimeTaskItem["state"], string> = {
  queued: "排队中", running: "执行中", completed: "已完成", failed: "失败", cancelled: "已取消", skipped: "已跳过",
};
export type RuntimeAction = "up" | "down" | "pause" | "resume" | "remove";
function RuntimeItems({ items, pending, onAction }: { items: RuntimeTaskItem[]; pending: boolean; onAction?: (id: string, action: RuntimeAction) => void }) {
  const ordered = [...items].sort((a, b) => (a.position ?? Infinity) - (b.position ?? Infinity));
  const queued = ordered.filter(item => item.state === "queued");
  return <ul className="runtime-task-list">{ordered.map(item => <li key={item.id}>
    <div className={`runtime-task is-${item.state}`}>
      <div className="runtime-task-line"><strong className="runtime-task-title">{item.title}</strong><span>{item.continuationFallback ? "承接异常 · 待确认" : item.paused ? "已挂起" : item.statusNote ?? stateLabels[item.state]}</span>{item.elapsedSeconds != null && <span>{formatElapsed(item.elapsedSeconds)}</span>}
        {onAction && item.state !== "running" && <div className="runtime-task-actions">
          {item.state === "queued" && <>
            <Button size="icon" disabled={pending || queued[0]?.id === item.id} aria-label={`上移 ${item.title}`} title="上移" onClick={() => onAction(item.id, "up")}><ArrowUp size={14} /></Button>
            <Button size="icon" disabled={pending || queued.at(-1)?.id === item.id} aria-label={`下移 ${item.title}`} title="下移" onClick={() => onAction(item.id, "down")}><ArrowDown size={14} /></Button>
            <Button size={item.continuationFallback ? undefined : "icon"} disabled={pending} aria-label={`${item.continuationFallback ? "继续生成（不承接）" : item.paused ? "恢复" : "挂起"} ${item.title}`} title={item.continuationFallback ? "继续生成（不承接）" : item.paused ? "恢复" : "挂起"} onClick={() => onAction(item.id, item.paused ? "resume" : "pause")}>{item.paused ? <Play size={14} /> : <Pause size={14} />}{item.continuationFallback && "继续生成（不承接）"}</Button>
          </>}
          <Button size="icon" disabled={pending} aria-label={`移除 ${item.title}`} title={item.state === "queued" ? "移出队列" : "移除记录，保留结果"} onClick={() => onAction(item.id, "remove")}><X size={14} /></Button>
        </div>}
      </div>
      {item.error && <p className="runtime-task-error">{item.error}</p>}
    </div>
  </li>)}</ul>;
}
export function RuntimeCenter({ projects, runtime, onCancel, onRetry, onCancelVideos, onProjectCancel, onProjectRetry, onProjectCancelVideos, onTaskAction }: {
  onTaskAction?: (projectId: string, kind: "prompt" | "video", jobId: string, action: RuntimeAction) => Promise<void>;
  projects?: ProjectRuntimeView[];
  runtime?: ProjectWorkspaceView["runtime"];
  onCancel?: (batchId: string) => Promise<void>;
  onRetry?: (batchId: string) => Promise<void>;
  onCancelVideos?: (jobIds: string[]) => Promise<void>;
  onProjectCancel?: (projectId: string, batchId: string) => Promise<void>;
  onProjectRetry?: (projectId: string, batchId: string) => Promise<void>;
  onProjectCancelVideos?: (projectId: string, jobIds: string[]) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<string>();
  const pendingRef = useRef(false);
  const [error, setError] = useState("");
  const entries = projects ?? (runtime ? [{ project: { id: "current", title: "当前项目" }, runtime }] : []);
  const failures = entries.reduce((sum, entry) => sum + (entry.runtime.promptBatches ?? []).reduce((n, b) => n + b.failedCount, 0) + (entry.runtime.videoJobs ?? []).filter(j => j.state === "failed").length, 0);
  const act = async (key: string, action: () => Promise<void>) => {
    if (pendingRef.current) return;
    pendingRef.current = true; setPending(key); setError("");
    try { await action(); }
    catch { setError("操作未确认，请检查运行状态后重试。"); }
    finally { pendingRef.current = false; setPending(undefined); }
  };
  return <>
    <Button onClick={() => setOpen(true)} aria-label="运行中心">运行中心{failures > 0 && ` · 失败 ${failures}`}</Button>
    <Dialog open={open} icon="runtime" title="运行中心" onClose={() => setOpen(false)}>
      <div className="runtime-center">
        {error && <p role="alert" className="runtime-task-error">{error}</p>}
        {pending && <span role="status">处理中…</span>}
        <div className="runtime-history">
          {!entries.length && <p className="runtime-empty">暂无项目运行记录</p>}
          {entries.map(({ project, runtime: value }) => {
            const batches = value.promptBatches ?? [];
            const videos = value.videoJobs ?? [];
            const queued = videos.filter(item => item.state === "queued").map(item => item.id);
            const prompts = batches.flatMap(batch => batch.items);
            return <details className="runtime-project" key={project.id} open>
              <summary className="runtime-project-summary"><span className="runtime-heading"><FolderOpen className="runtime-project-icon" size={19} aria-hidden="true" /><span className="runtime-heading-title">{project.title}</span></span></summary>
              <section className="runtime-section" aria-label="提示词增强记录"><details className="runtime-category is-prompt" open>
                <summary className="runtime-batch-summary"><span className="runtime-heading"><Sparkles size={16} aria-hidden="true" /><span className="runtime-heading-title">提示词增强</span><span className="runtime-heading-count">{prompts.length} 项</span></span></summary>
                {batches.filter(batch => batch.queuedCount > 0 || batch.failedCount > 0).map(batch => <div className="runtime-batch-actions" key={batch.id}>
                  <span>{new Date(batch.createdAt).toLocaleString("zh-CN")}</span>
                  {batch.queuedCount > 0 && (onProjectCancel || onCancel) && <Button disabled={Boolean(pending)} onClick={() => void act(batch.id, () => onProjectCancel ? onProjectCancel(project.id, batch.id) : onCancel!(batch.id))}>取消待执行项</Button>}
                  {batch.failedCount > 0 && (onProjectRetry || onRetry) && <Button disabled={Boolean(pending)} onClick={() => void act(batch.id, () => onProjectRetry ? onProjectRetry(project.id, batch.id) : onRetry!(batch.id))}>重试失败项</Button>}
                </div>)}
                {prompts.length ? <RuntimeItems items={prompts} pending={Boolean(pending)} onAction={onTaskAction ? (id, action) => void act(id, () => onTaskAction(project.id, "prompt", id, action)) : undefined} /> : <p className="runtime-empty">暂无提示词增强记录</p>}
              </details></section>
              <section className="runtime-section" aria-label="视频生成记录"><details className="runtime-category is-video" open>
                <summary className="runtime-batch-summary"><span className="runtime-heading"><Film size={16} aria-hidden="true" /><span className="runtime-heading-title">视频生成</span><span className="runtime-heading-count">{videos.length} 项</span></span></summary>
                {queued.length > 0 && (onProjectCancelVideos || onCancelVideos) && <div className="runtime-batch-actions"><Button disabled={Boolean(pending)} onClick={() => void act(project.id + ":videos", () => onProjectCancelVideos ? onProjectCancelVideos(project.id, queued) : onCancelVideos!(queued))}>取消待执行视频</Button></div>}
                {videos.length ? <RuntimeItems items={videos} pending={Boolean(pending)} onAction={onTaskAction ? (id, action) => void act(id, () => onTaskAction(project.id, "video", id, action)) : undefined} /> : <p className="runtime-empty">暂无视频生成记录</p>}
              </details></section>
            </details>;
          })}
        </div>
      </div>
    </Dialog>
  </>;
}
