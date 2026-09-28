import { useEffect, useState } from "react";
import type { LifecycleGateway, LifecycleScope } from "../../gateways/lifecycleGateway";
import { readOnlyProjectGateway } from "../../gateways/readOnlyProjectGateway";
import type { TaskSummary } from "../../gateways/projectGateway";
import type { ProjectAsset } from "../../domain/storyboard";
import { Button, SegmentedControl } from "../../ui/primitives";
import { Dialog } from "../../ui/overlay";
import { TaskReadOnlyDialog } from "./TaskReadOnlyDialog";
import "./ProjectReadOnly.css";

export function ProjectReadOnlyBrowser({ projectId, title, lifecycle, onClose }: {
  projectId: string; title: string; lifecycle: LifecycleGateway; onClose: () => void;
}) {
  const [scope, setScope] = useState<LifecycleScope | "assets">("active");
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [task, setTask] = useState<TaskSummary | null>(null);
  const [asset, setAsset] = useState<ProjectAsset | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(""); setTasks([]); setAssets([]);
    const load = async () => {
      if (scope === "assets") {
        const items = await readOnlyProjectGateway.assets(projectId);
        if (!cancelled) setAssets(items);
      } else {
        const workspace = await lifecycle.getWorkspace(projectId, scope);
        if (!cancelled) setTasks(workspace.tasks);
      }
    };
    load().catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "项目加载失败"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectId, scope, lifecycle, attempt]);
  return <>
    <Dialog open icon="history" title={`只读项目 · ${title}`} onClose={onClose}>
      <div className="project-readonly-browser">
        <p>这里只查看和下载；编辑或生成前，请恢复项目并取消归档。</p>
        <SegmentedControl value={scope} ariaLabel="只读项目内容" options={[
          { value: "active", label: "任务" }, { value: "archived", label: "归档任务" },
          { value: "trash", label: "回收站" }, { value: "assets", label: "资产" },
        ]} onChange={setScope} />
        {loading && <p role="status">正在加载…</p>}
        {error && <div role="alert">{error}<Button onClick={() => setAttempt(value => value + 1)}>重试</Button></div>}
        {!loading && !error && !tasks.length && !assets.length && <p>这里没有内容。</p>}
        <div className="project-readonly-list">
          {tasks.map(item => <div className="project-readonly-row" key={item.id}><strong>{item.title}</strong><Button onClick={() => setTask(item)}>查看任务</Button></div>)}
          {assets.map(item => <div className="project-readonly-row" key={item.id}><strong>{item.name}</strong><Button onClick={() => setAsset(item)}>查看资产</Button></div>)}
        </div>
      </div>
    </Dialog>
    {task && <TaskReadOnlyDialog projectId={projectId} taskId={task.id} title={task.title} onClose={() => setTask(null)} />}
    {asset && <Dialog open icon="assets" title={`只读资产 · ${asset.name}`} onClose={() => setAsset(null)}>
      <div className="project-readonly-asset">
        {asset.mediaType === "image" ? <img src={asset.mediaUrl} alt={asset.name} /> : asset.mediaType === "audio" ? <audio controls src={asset.mediaUrl} /> : <video controls src={asset.mediaUrl} poster={asset.previewUrl} />}
        <a href={asset.mediaUrl} download={asset.originalFilename}>下载资产</a>
      </div>
    </Dialog>}
  </>;
}
