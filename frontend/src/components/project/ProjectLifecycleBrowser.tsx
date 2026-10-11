import { useCallback, useEffect, useState } from "react";
import type { LifecycleGateway } from "../../gateways/lifecycleGateway";
import type { ProjectSummary } from "../../gateways/projectGateway";
import { Button } from "../../ui/primitives";
import { Dialog } from "../../ui/overlay";
import "./ProjectLifecycle.css";
import { ProjectReadOnlyBrowser } from "./ProjectReadOnlyBrowser";
import { ProjectExportDialog } from "./ProjectExportDialog";
import { projectTransferGateway } from "../../gateways/projectTransferGateway";
import { importConfigurationGateway } from "../../gateways/importConfigurationGateway";
import { ImportConfigurationDialog } from "./ImportConfigurationDialog";

export function ProjectLifecycleBrowser({ gateway, onClose, onChanged }: {
  gateway: LifecycleGateway; onClose: () => void; onChanged: () => Promise<void>;
}) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [deleting, setDeleting] = useState<ProjectSummary | null>(null);
  const [preview, setPreview] = useState<ProjectSummary | null>(null);
  const [exportProject, setExportProject] = useState<ProjectSummary | null>(null);
  const [configureProject, setConfigureProject] = useState<ProjectSummary | null>(null);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError("");
    gateway.listProjects().then(items => { if (!cancelled) setProjects(items); })
      .catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "项目加载失败"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [gateway, revision]);
  const changed = useCallback(async () => {
    await onChanged();
    setRevision(value => value + 1);
  }, [onChanged]);
  return <>
    <Dialog open icon="configure" title="项目管理" onClose={onClose}>
      <div className="project-lifecycle-browser">
        {loading && <p role="status">正在加载…</p>}
        {error && <div role="alert">{error}<Button onClick={() => setRevision(value => value + 1)}>重试</Button></div>}
        {!loading && !error && !projects.length && <p>这里没有项目。</p>}
        <div className="project-lifecycle-rows" aria-label="项目管理列表">
          {projects.map(project => <div className="project-lifecycle-row" key={project.id}>
            <div className="project-lifecycle-details"><strong>{project.title}</strong><span>{project.taskCount} 个任务 · {project.assetCount} 个资产</span></div>
            <div className="project-lifecycle-actions">
              <Button onClick={() => setPreview(project)}>查看</Button>
              <Button onClick={() => setExportProject(project)}>导出</Button>
              <Button onClick={() => setConfigureProject(project)}>确认生成配置</Button>
              <Button onClick={() => setDeleting(project)}>移除项目</Button>
            </div>
          </div>)}
        </div>
      </div>
    </Dialog>
    {deleting && <ProjectLifecycleConfirmation gateway={gateway} project={deleting}
      onClose={() => setDeleting(null)} onChanged={changed} />}
    {preview && <ProjectReadOnlyBrowser projectId={preview.id} title={preview.title} lifecycle={gateway} onClose={() => setPreview(null)} />}
    {exportProject && <ProjectExportDialog project={exportProject} gateway={projectTransferGateway}
      onClose={() => setExportProject(null)} />}
    {configureProject && <ImportConfigurationDialog projectId={configureProject.id}
      gateway={importConfigurationGateway} onClose={() => setConfigureProject(null)} />}
  </>;
}

export function ProjectLifecycleConfirmation({ gateway, project, onClose, onChanged }: {
  gateway: LifecycleGateway; project: ProjectSummary; onClose: () => void; onChanged: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [committed, setCommitted] = useState(false);
  const [error, setError] = useState("");
  const submit = async () => {
    if (busy) return;
    setBusy(true); setError("");
    let saved = committed;
    try {
      if (!saved) {
        await gateway.removeProject(project.id);
        saved = true; setCommitted(true);
      }
      await onChanged(); onClose();
    } catch (reason) {
      setError(saved ? "项目已移除，但列表刷新失败。请重试刷新。"
        : reason instanceof Error ? reason.message : "移除未完成，请重试。");
    } finally { setBusy(false); }
  };
  return <Dialog open icon="delete" title="移除项目" onClose={() => { if (!busy) onClose(); }}>
    <div className="project-lifecycle-confirmation">
      <strong>{project.title}</strong>
      <p>确定从工作台移除这个项目吗？工程文件、生成结果和本机原始素材仍保留在原位置，可通过“打开工程”重新载入。</p>
      {error && <p role="alert">{error}</p>}
      <footer className="project-lifecycle-actions"><Button disabled={busy} onClick={onClose}>取消</Button>
        <Button variant="accent" disabled={busy} onClick={() => void submit()}>{busy ? "移除中…" : committed ? "重试刷新" : "确认移除"}</Button></footer>
    </div>
  </Dialog>;
}
