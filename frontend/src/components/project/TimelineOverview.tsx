import { useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { Button, TextField } from "../../ui/primitives";
import { Dialog } from "../../ui/overlay";
import { listTasksInStoryOrder } from "../../domain/storyboard";
import type { ProjectGateway } from "../../gateways/projectGateway";
import type { DirectorProject } from "./projectTypes";
import { TaskPreview } from "./TaskPreview";

export function TimelineOverview({ project, gateway, onRefresh, onOpen }: {
  project: DirectorProject;
  gateway: ProjectGateway;
  onRefresh: () => Promise<void>;
  onOpen: (id: string) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const create = async () => {
    setBusy(true); setError("");
    try {
      const numbers = new Set(project.snapshot.scenes.map(scene => scene.title));
      let number = project.snapshot.scenes.length + 1;
      while (numbers.has(`时间线 ${number}`)) number += 1;
      await gateway.createTimeline(project.id, `时间线 ${number}`);
      await onRefresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "新建时间线失败"); }
    finally { setBusy(false); }
  };
  const save = async () => {
    const title = name.trim() || `时间线 ${project.snapshot.scenes.length + 1}`;
    setBusy(true); setError("");
    try {
      if (editing) {
        await gateway.renameTimeline(project.id, editing, title);
        await onRefresh();
        setEditing(null);
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "保存时间线失败"); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    if (!deleting) return;
    setBusy(true); setError("");
    try { await gateway.deleteTimeline(project.id, deleting); await onRefresh(); setDeleting(null); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "删除时间线失败"); }
    finally { setBusy(false); }
  };
  return <div className="task-list-view timeline-overview">
    <button type="button" className="task-list-row is-create" disabled={busy} onClick={() => void create()} aria-label="新建时间线">
      <div className="task-preview is-compact"><Plus size={24} /></div>
      <div className="task-list-copy"><strong>新建时间线</strong></div>
      <div className="task-list-stats"><span>{project.snapshot.scenes.length} 条时间线</span></div>
      <div className="task-list-status"><Plus size={14} />新建</div>
    </button>
    {project.snapshot.scenes.map((scene, index) => {
      const tasks = listTasksInStoryOrder(project.snapshot, scene.id);
      const duration = tasks.reduce((value, task) => Math.max(value, (task.timelineStartSeconds ?? value) + task.plannedDurationSeconds), 0);
      const first = tasks.find(task => task.storyboardFrame.previewUrl) ?? tasks[0];
      return <div key={scene.id} className="task-collection-item is-list timeline-overview-item">
        <div className="task-item-content"><button type="button" className="task-list-row" onClick={() => onOpen(scene.id)} onDoubleClick={() => onOpen(scene.id)}>
          {first ? <TaskPreview previewUrl={first.storyboardFrame.previewUrl} compact /> : <div className="task-preview is-compact"><span>{index + 1}</span></div>}
          <div className="task-list-copy"><div className="task-list-heading"><strong>{scene.title || `时间线 ${index + 1}`}</strong></div><span className="task-list-params">{tasks.length} 个片段 · {duration.toFixed(1)} 秒</span></div>
          <div className="task-list-stats"><span>{tasks.filter(task => task.primaryResultId).length} 个片段有结果</span></div>
          <div className="task-list-status">打开时间线</div>
        </button></div>
        <div className="timeline-row-actions"><Button size="icon" aria-label={`重命名 ${scene.title}`} onClick={() => { setEditing(scene.id); setName(scene.title); }}><Pencil size={15} /></Button><Button size="icon" aria-label={`删除 ${scene.title}`} onClick={() => setDeleting(scene.id)}><Trash2 size={15} /></Button></div>
        {editing === scene.id && <div className="timeline-name-editor"><TextField value={name} onChange={setName} placeholder="时间线名称" /><Button disabled={busy} onClick={() => void save()}>保存</Button><Button onClick={() => setEditing(null)}>取消</Button></div>}
      </div>;
    })}
    {error && <p role="alert">{error}</p>}
    <Dialog open={!!deleting} icon="delete" title="删除时间线" onClose={() => setDeleting(null)}><p>只可删除空时间线。片段和结果不会被自动删除。</p><div className="task-lifecycle-actions"><Button onClick={() => setDeleting(null)}>取消</Button><Button variant="accent" disabled={busy} onClick={() => void remove()}>确认删除</Button></div></Dialog>
  </div>;
}
