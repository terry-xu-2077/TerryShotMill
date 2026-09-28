import { useCallback, useEffect, useState } from "react";
import type { LifecycleAction, LifecycleGateway, LifecycleScope } from "../../gateways/lifecycleGateway";
import type { ProjectSummary } from "../../gateways/projectGateway";
import { Button, Checkbox, SegmentedControl } from "../../ui/primitives";
import { Dialog } from "../../ui/overlay";
import "./ProjectLifecycle.css";
import { ProjectReadOnlyBrowser } from "./ProjectReadOnlyBrowser";
import { ProjectExportDialog } from "./ProjectExportDialog";
import { projectTransferGateway } from "../../gateways/projectTransferGateway";
import { importConfigurationGateway } from "../../gateways/importConfigurationGateway";
import { ImportConfigurationDialog } from "./ImportConfigurationDialog";

type Intent = { project: ProjectSummary; action: LifecycleAction | "purge" };
const labels = { archive: "归档项目", unarchive: "取消归档", trash: "删除项目", restore: "恢复项目", purge: "永久删除项目" };

export function ProjectLifecycleBrowser({ gateway, initialScope = "active", onClose, onChanged }: {
  gateway: LifecycleGateway; initialScope?: LifecycleScope; onClose: () => void; onChanged: () => Promise<void>;
}) {
  const [scope, setScope] = useState<LifecycleScope>(initialScope);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [intent, setIntent] = useState<Intent | null>(null);
  const [preview, setPreview] = useState<ProjectSummary | null>(null);
  const [exportProject, setExportProject] = useState<ProjectSummary | null>(null);
  const [configureProject, setConfigureProject] = useState<ProjectSummary | null>(null);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(""); setProjects([]);
    gateway.listProjects(scope).then(items => { if (!cancelled) setProjects(items); })
      .catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "项目加载失败"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [gateway, scope, revision]);
  const changed = useCallback(async () => {
    await onChanged();
    setRevision(value => value + 1);
  }, [onChanged]);
  return <>
    <Dialog open icon="history" title="项目管理" onClose={onClose}>
      <div className="project-lifecycle-browser">
        <SegmentedControl value={scope} ariaLabel="项目存放位置" options={[
          { value: "active", label: "当前项目" }, { value: "archived", label: "已归档" }, { value: "trash", label: "回收站" },
        ]} onChange={setScope} />
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
              <Button onClick={() => setIntent({ project, action: scope === "active" ? "archive" : scope === "archived" ? "unarchive" : "restore" })}>
                {scope === "active" ? "归档" : scope === "archived" ? "取消归档" : "恢复"}
              </Button>
              <Button onClick={() => setIntent({ project, action: scope === "trash" ? "purge" : "trash" })}>{scope === "trash" ? "永久删除" : "删除"}</Button>
            </div>
          </div>)}
        </div>
      </div>
    </Dialog>
    {intent && <ProjectLifecycleConfirmation gateway={gateway} intent={intent} onClose={() => setIntent(null)} onChanged={changed} />}
    {preview && <ProjectReadOnlyBrowser projectId={preview.id} title={preview.title} lifecycle={gateway} onClose={() => setPreview(null)} />}
    {exportProject && <ProjectExportDialog project={exportProject} gateway={projectTransferGateway}
      onClose={() => setExportProject(null)} />}
    {configureProject && <ImportConfigurationDialog projectId={configureProject.id}
      gateway={importConfigurationGateway} onClose={() => setConfigureProject(null)} />}
  </>;
}

export function ProjectLifecycleConfirmation({ gateway, intent, onClose, onChanged }: {
  gateway: LifecycleGateway; intent: Intent; onClose: () => void; onChanged: () => Promise<void>;
}) {
  const [archiveResults, setArchiveResults] = useState(true);
  const [busy, setBusy] = useState(false);
  const [committed, setCommitted] = useState(false);
  const [error, setError] = useState("");
  const submit = async () => {
    if (busy) return;
    setBusy(true); setError("");
    let saved = committed;
    try {
      if (!saved) {
        if (intent.action === "purge") await gateway.purgeProject(intent.project.id, archiveResults);
        else await gateway.transitionProject(intent.project.id, intent.action);
        saved = true; setCommitted(true);
      }
      await onChanged(); onClose();
    } catch (reason) {
      setError(saved ? "操作已完成，但列表刷新失败。请重试刷新。" : reason instanceof Error ? reason.message : "操作未完成，请重试。");
    } finally { setBusy(false); }
  };
  return <Dialog open icon={intent.action === "trash" || intent.action === "purge" ? "delete" : "history"}
    title={labels[intent.action]} onClose={() => { if (!busy) onClose(); }}>
    <div className="project-lifecycle-confirmation">
      <strong>{intent.project.title}</strong>
      {intent.action === "archive" && <p>归档后保留全部任务、资产和结果；编辑或生成前需要取消归档。</p>}
      {intent.action === "unarchive" && <p>项目返回当前项目列表，任务原有的归档和回收站状态保持不变。</p>}
      {intent.action === "trash" && <p>整个项目移入回收站，全部任务、资产和生成结果保留，可随时恢复。</p>}
      {intent.action === "restore" && <p>恢复项目此前的状态；此前单独删除的任务仍留在任务回收站。</p>}
      {intent.action === "purge" && <>
        <p>永久删除整个项目及其任务、项目内资产，无法恢复。其他项目已导入的独立副本不受影响。</p>
        <div className="project-lifecycle-option"><Checkbox checked={archiveResults} onChange={setArchiveResults}
          disabled={busy || committed} ariaLabel="归档全部生成结果后删除" /><span>归档全部生成结果后删除</span></div>
        <p>{archiveResults ? "保留所有生成版本，可从首页“生成结果归档”找回。归档失败则不会删除项目。" : "未归档的全部生成结果也将永久删除。"}</p>
      </>}
      {error && <p role="alert">{error}</p>}
      <footer className="project-lifecycle-actions"><Button disabled={busy} onClick={onClose}>取消</Button>
        <Button variant="accent" disabled={busy} onClick={() => void submit()}>{busy ? "处理中…" : committed ? "重试刷新" : labels[intent.action]}</Button></footer>
    </div>
  </Dialog>;
}
