import { useCallback, useEffect, useState, type ReactNode } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";

import type { GenerationTask } from "./domain/storyboard";
import {
  httpProjectGateway,
  type ProjectGateway,
  type ApplicationSettings,
  type ProjectSettings,
  type ProjectSummary,
} from "./gateways/projectGateway";
import {
  batchReviewGateway,
  type PromptReviewItem,
} from "./gateways/batchReviewGateway";
import {
  mapTaskEditor,
  mapWorkspaceProject,
  taskSaveInput,
} from "./gateways/projectGatewayMapper";
import { ProjectWorkspace } from "./components/project/ProjectWorkspace";
import { CreateProjectDialog, OpenProjectDialog, ProjectHome } from "./components/project/ProjectHome";
import type { DirectorProject } from "./components/project/projectTypes";
import { BridgeStatus } from "./components/project/BridgeStatus";
import { ProjectLifecycleBrowser } from "./components/project/ProjectLifecycleBrowser";
import { projectTransferGateway } from "./gateways/projectTransferGateway";
import { ProjectImportDialog } from "./components/project/ProjectImportDialog";

import { GlobalStatusbar } from "./components/project/GlobalStatusbar";
import { lifecycleGateway as defaultLifecycleGateway, type LifecycleGateway } from "./gateways/lifecycleGateway";

type AppProps = {
  gateway?: ProjectGateway;
  lifecycle?: LifecycleGateway;
};

export function App({ gateway = httpProjectGateway, lifecycle = defaultLifecycleGateway }: AppProps) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [currentProject, setCurrentProject] = useState<DirectorProject | null>(null);
  const [promptReviewItems, setPromptReviewItems] = useState<PromptReviewItem[]>([]);
  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [openProjectFileDialog, setOpenProjectFileDialog] = useState(false);
  const [importProjectOpen, setImportProjectOpen] = useState(false);
  const [projectManagementOpen, setProjectManagementOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [applicationSettings, setApplicationSettings] = useState<ApplicationSettings>();
  const loadBridgeStatus = useCallback((signal?: AbortSignal) => gateway.getComfyUIStatus(signal), [gateway]);
  const chooseProjectFile = useCallback(async (save: boolean) =>
    isTauri() ? invoke<string | null>("choose_project_file", { save }) : null, []);
  const bridgeStatus = <BridgeStatus load={loadBridgeStatus} address={applicationSettings?.comfyui.baseUrl} />;

  const refreshProjects = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      setProjects(await gateway.listProjects());
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "项目列表加载失败");
    } finally {
      setLoading(false);
    }
  }, [gateway]);

  const loadPromptReviewState = useCallback(async (projectId: string) => {
    try {
      const state = await batchReviewGateway.getPromptReviewState(projectId);
      setPromptReviewItems(state.items);
      return state.items;
    } catch {
      // V0.4 target contract may lead the production backend or an injected in-memory gateway.
      // In that transition state the legacy workspace remains usable and simply shows pending review.
      setPromptReviewItems([]);
      return [];
    }
  }, []);

  const loadProject = useCallback(async (projectId: string) => {
    const [settings, workspace, assets] = await Promise.all([
      gateway.getProjectSettings(projectId),
      gateway.getWorkspace(projectId),
      gateway.listAssets(projectId),
      loadPromptReviewState(projectId),
    ]);
    const project = mapWorkspaceProject(settings, workspace, assets);
    setCurrentProject(project);
    return project;
  }, [gateway, loadPromptReviewState]);

  useEffect(() => {
    void refreshProjects();
  }, [refreshProjects]);

  useEffect(() => {
    void gateway.getApplicationSettings().then(setApplicationSettings).catch(() => {
      // Keep the workspace available; the settings dialog will show its loading state.
    });
  }, [gateway]);

  const currentProjectId = currentProject?.id;
  useEffect(() => {
    if (!currentProjectId) return;
    let refreshPending = false;
    let refreshAgain = false;
    let disposed = false;
    const unsubscribe = gateway.subscribeProject(currentProjectId, () => {
      refreshAgain = true;
      if (refreshPending) return;
      refreshPending = true;
      void (async () => {
        try {
          do {
            refreshAgain = false;
            try {
              await Promise.all([loadProject(currentProjectId), refreshProjects()]);
            } catch (error) {
              if (!disposed) setLoadError(error instanceof Error ? error.message : "运行状态更新失败");
            }
          } while (refreshAgain && !disposed);
        } finally {
          refreshPending = false;
        }
      })();
    });
    return () => { disposed = true; unsubscribe(); };
  }, [currentProjectId, gateway, loadProject, refreshProjects]);

  const reloadCurrentProject = useCallback(async () => {
    if (!currentProject) return;
    await Promise.all([loadProject(currentProject.id), refreshProjects()]);
  }, [currentProject, loadProject, refreshProjects]);

  const saveProjectConfiguration = async (settings: Pick<ProjectSettings, "title" | "description" | "useDescriptionForAiPrompt" | "cover">) => {
    if (!currentProject) return;
    await gateway.updateProject(currentProject.id, settings);
    await reloadCurrentProject();
  };

  const shell = (content: ReactNode) => <div className="application-shell">
    <div className="application-content">{content}</div>
    <GlobalStatusbar gateway={gateway} settings={applicationSettings} refreshKey={currentProject ?? projects}
      onSaveSettings={async next => { setApplicationSettings(await gateway.updateApplicationSettings(next)); }} />
  </div>;

  if (!currentProject) {
    return shell(
      <>
      <ProjectHome
          bridgeStatus={bridgeStatus}
          projects={projects}
          loading={loading}
          error={loadError}
          onRetry={() => void refreshProjects()}
          onOpenProject={(projectId) => {
            void loadProject(projectId).catch((error) => {
              setLoadError(error instanceof Error ? error.message : "项目加载失败");
            });
          }}
          onCreateProject={() => { setLoadError(""); setCreateProjectOpen(true); }}
          onOpenProjectFile={() => {
            if (isTauri()) {
              void chooseProjectFile(false).then(path => {
                if (!path) return;
                void gateway.openProjectFile(path).then(async project => {
                  await refreshProjects();
                  await loadProject(project.id);
                }).catch(error => setLoadError(error instanceof Error ? error.message : "工程文件打开失败"));
              });
            } else { setLoadError(""); setOpenProjectFileDialog(true); }
          }}
          onImportProject={() => setImportProjectOpen(true)}
          onManageProjects={() => setProjectManagementOpen(true)}
        />
        {importProjectOpen && <ProjectImportDialog gateway={projectTransferGateway}
          onBrowsePath={isTauri() ? () => chooseProjectFile(true) : undefined}
          onClose={() => { setImportProjectOpen(false); void refreshProjects(); }}
          onChanged={async () => { setProjects(await gateway.listProjects()); }} />}
        {projectManagementOpen && <ProjectLifecycleBrowser gateway={lifecycle}
          onClose={() => setProjectManagementOpen(false)} onChanged={async () => {
            setProjects(await gateway.listProjects());
          }} />}
        <CreateProjectDialog
          open={createProjectOpen}
          onClose={() => setCreateProjectOpen(false)}
          error={loadError}
          onBrowsePath={isTauri() ? () => chooseProjectFile(true) : undefined}
          onCreate={(title, path) => {
            void gateway.createProject({ title, path }).then(async (project) => {
              setCreateProjectOpen(false);
              await refreshProjects();
              await loadProject(project.id);
            }).catch((error) => {
              setLoadError(error instanceof Error ? error.message : "项目创建失败");
            });
          }}
        />
        <OpenProjectDialog open={openProjectFileDialog}
          onClose={() => setOpenProjectFileDialog(false)}
          error={loadError}
          onBrowsePath={isTauri() ? () => chooseProjectFile(false) : undefined}
          onOpen={path => {
            void gateway.openProjectFile(path).then(async project => {
              setOpenProjectFileDialog(false);
              await refreshProjects();
              await loadProject(project.id);
            }).catch(error => setLoadError(error instanceof Error ? error.message : "工程文件打开失败"));
          }} />
      </>
    );
  }

  return shell(
    <ProjectWorkspace
      lifecycleGateway={lifecycle}
      onLifecycleChanged={reloadCurrentProject}
      bridgeStatus={bridgeStatus}
      project={currentProject}
      applicationSettings={applicationSettings}
      promptReviewItems={promptReviewItems}
      onBack={() => {
        setCurrentProject(null);
        setPromptReviewItems([]);
        void refreshProjects();
      }}
      onLoadTaskEditor={async (taskId) => {
        const [editor, revisions] = await Promise.all([
          gateway.getTaskEditor(currentProject.id, taskId),
          gateway.listPromptRevisions(currentProject.id, taskId),
        ]);
        const fallback = currentProject.snapshot.tasks.find((task) => task.id === taskId);
        return mapTaskEditor(editor, revisions, fallback);
      }}
      onCreateTask={async (task: GenerationTask) => {
        const input = taskSaveInput(task);
        if (currentProject.snapshot.tasks.length === 0) input.generation.contextMode = "不承接";
        const created = await gateway.createTask(currentProject.id, input);
        await reloadCurrentProject();
        return created.id;
      }}
      onUpdateTask={async (task) => {
        await gateway.updateTask(currentProject.id, task.id, taskSaveInput(task));
        await reloadCurrentProject();
      }}
      gateway={gateway}
      onRefreshProject={reloadCurrentProject}
      onSaveProjectConfiguration={saveProjectConfiguration}
      onChooseLocalFiles={isTauri() ? () => invoke<string[]>("choose_asset_files") : undefined}
      onEnhancePrompt={(request) => gateway.enhancePrompt(currentProject.id, request)}
      onBatchEnhancePrompts={async (request) => {
        const response = await batchReviewGateway.batchEnhancePrompts(currentProject.id, request);
        await reloadCurrentProject();
        return response;
      }}
      onCheckPromptBatchEligibility={(taskIds) => batchReviewGateway.checkPromptBatchEligibility(currentProject.id, taskIds)}
      onApprovePrompt={async (taskId) => {
        const result = await batchReviewGateway.approvePrompt(currentProject.id, taskId);
        await loadPromptReviewState(currentProject.id);
        return result;
      }}
      onCancelPromptBatch={async (batchId) => {
        await batchReviewGateway.cancelPromptBatch(currentProject.id, batchId);
        await reloadCurrentProject();
      }}
      onVideoVersionChanged={reloadCurrentProject}
      onStopVideoJob={async (jobId) => {
        await batchReviewGateway.stopVideoJob(currentProject.id, jobId);
        await reloadCurrentProject();
      }}
      onCancelQueuedVideos={async (jobIds) => {
        await batchReviewGateway.cancelQueuedVideos(currentProject.id, jobIds);
        await reloadCurrentProject();
      }}
      onUpdateEditorPreference={async (taskId, preference) => {
        await gateway.updateEditorPreference(currentProject.id, taskId, preference);
      }}
      onRetryFailedPromptBatch={async (batchId) => {
        await batchReviewGateway.retryFailedPromptBatch(currentProject.id, batchId);
        await reloadCurrentProject();
      }}
      onCheckVideoBatchEligibility={(taskIds) => (
        batchReviewGateway.checkVideoBatchEligibility(currentProject.id, taskIds)
      )}
      onCreateVideoBatch={async (taskIds) => {
        const result = await batchReviewGateway.createVideoBatch(currentProject.id, taskIds);
        await reloadCurrentProject();
        return result;
      }}
      onSaveApplicationSettings={async (next) => {
        setApplicationSettings(await gateway.updateApplicationSettings(next));
      }}
      onRefreshComfyUIWorkflows={() => gateway.listComfyUIWorkflows()}
    />
  );
}
