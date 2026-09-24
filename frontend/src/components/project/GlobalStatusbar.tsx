import { Settings } from "lucide-react";
import { useEffect, useState } from "react";
import type { ApplicationSettings, ProjectGateway, ProjectRuntimeView } from "../../gateways/projectGateway";
import { batchReviewGateway } from "../../gateways/batchReviewGateway";
import { Dialog } from "../../ui/overlay";
import { ApplicationSettingsPanel } from "../settings/ApplicationSettingsPanel";
import { RuntimeCenter } from "./RuntimeCenter";

export function GlobalStatusbar({ gateway, settings, onSaveSettings, refreshKey }: {
  gateway: ProjectGateway;
  settings?: ApplicationSettings;
  onSaveSettings: (settings: ApplicationSettings) => Promise<void>;
  refreshKey?: unknown;
}) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [projects, setProjects] = useState<ProjectRuntimeView[]>([]);
  const [error, setError] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const next = await gateway.getGlobalRuntime();
        if (active) { setProjects(next); setError(false); setLoaded(true); }
      } catch { if (active) setError(true); }
      finally { if (active) timer = setTimeout(() => void refresh(), 5000); }
    };
    void refresh();
    return () => { active = false; clearTimeout(timer); };
  }, [gateway, refreshKey, revision]);
  const items = projects.flatMap(project => [...(project.runtime.videoJobs ?? []), ...(project.runtime.promptBatches ?? []).flatMap(batch => batch.items)]);
  const running = items.filter(item => item.state === "running").length;
  const queued = items.filter(item => item.state === "queued" && !item.paused).length;
  const paused = items.filter(item => item.paused).length;
  const action = async (run: () => Promise<unknown>) => { await run(); setRevision(value => value + 1); };
  return <>
    <footer className="project-workspace-statusbar" aria-label="全局状态栏">
      <button type="button" onClick={() => setSettingsOpen(true)}><Settings size={16} strokeWidth={1.6} /> 设置</button>
      <div className="workspace-runtime-summary" role="status"><span className={running ? "workspace-running-dot" : "workspace-idle-dot"} />{error ? "运行状态更新失败，正在重连…" : !loaded ? "正在读取运行状态…" : running || queued || paused ? `执行中 ${running} 项 · 排队 ${queued} 项${paused ? ` · 挂起 ${paused} 项` : ""}` : "当前没有正在运行的任务"}</div>
      <div className="workspace-runtime-entry"><RuntimeCenter projects={projects}
        onTaskAction={(project, kind, job, command) => action(() => batchReviewGateway.runtimeAction(project, kind, job, command))}
        onProjectCancel={(id, batch) => action(() => batchReviewGateway.cancelPromptBatch(id, batch))}
        onProjectRetry={(id, batch) => action(() => batchReviewGateway.retryFailedPromptBatch(id, batch))}
        onProjectCancelVideos={(id, jobs) => action(() => batchReviewGateway.cancelQueuedVideos(id, jobs))} /></div>
    </footer>
    <Dialog open={settingsOpen} icon="settings" title="设置" onClose={() => setSettingsOpen(false)}><ApplicationSettingsPanel settings={settings} onClose={() => setSettingsOpen(false)} onSave={onSaveSettings} onRefreshComfyUIWorkflows={() => gateway.listComfyUIWorkflows()} /></Dialog>
  </>;
}
