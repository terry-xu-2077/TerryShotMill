import { useCallback, useEffect, useState } from "react";

import type { GenerationTask, ProjectAsset } from "./domain/storyboard";
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
import {
  CreateProjectDialog,
  ProjectHome,
  ProjectWorkspace,
} from "./features/projects/ProjectWorkspaceV2";
import type { DirectorProject } from "./mock/projects";

type AppProps = {
  gateway?: ProjectGateway;
};

export function App({ gateway = httpProjectGateway }: AppProps) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [currentProject, setCurrentProject] = useState<DirectorProject | null>(null);
  const [promptReviewItems, setPromptReviewItems] = useState<PromptReviewItem[]>([]);
  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [applicationSettings, setApplicationSettings] = useState<ApplicationSettings>();

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
    return gateway.subscribeProject(currentProjectId, () => {
      if (refreshPending) return;
      refreshPending = true;
      void Promise.all([loadProject(currentProjectId), refreshProjects()])
        .catch((error) => {
          setLoadError(error instanceof Error ? error.message : "运行状态更新失败");
        })
        .finally(() => {
          refreshPending = false;
        });
    });
  }, [currentProjectId, gateway, loadProject, refreshProjects]);

  const reloadCurrentProject = useCallback(async () => {
    if (!currentProject) return;
    await Promise.all([loadProject(currentProject.id), refreshProjects()]);
  }, [currentProject, loadProject, refreshProjects]);

  const saveProjectConfiguration = async (
    settings: Pick<ProjectSettings, "title" | "description" | "useDescriptionForAiPrompt">,
    assets: ProjectAsset[],
  ) => {
    if (!currentProject) return;
    const previousAssets = currentProject.snapshot.assets;
    const nextIds = new Set(assets.filter((asset) => !asset.sourceFile).map((asset) => asset.id));
    const removed = previousAssets.filter((asset) => !nextIds.has(asset.id));
    const retained = assets.filter((asset) => !asset.sourceFile);
    const added = assets.filter((asset) => asset.sourceFile);

    await gateway.updateProject(currentProject.id, settings);
    await Promise.all([
      ...removed.map((asset) => gateway.deleteAsset(currentProject.id, asset.id)),
      ...retained.map((asset) => gateway.updateAsset(currentProject.id, asset.id, {
        name: asset.name,
        category: asset.category,
        tags: asset.tags,
      })),
      ...added.map((asset) => gateway.importAsset(currentProject.id, asset.sourceFile!, {
        name: asset.name,
        category: asset.category,
        tags: asset.tags,
      })),
    ]);
    await reloadCurrentProject();
  };

  if (!currentProject) {
    return (
      <>
        <ProjectHome
          projects={projects}
          loading={loading}
          error={loadError}
          onRetry={() => void refreshProjects()}
          onOpenProject={(projectId) => {
            void loadProject(projectId).catch((error) => {
              setLoadError(error instanceof Error ? error.message : "项目加载失败");
            });
          }}
          onCreateProject={() => setCreateProjectOpen(true)}
        />
        <CreateProjectDialog
          open={createProjectOpen}
          onClose={() => setCreateProjectOpen(false)}
          onCreate={(title) => {
            void gateway.createProject({ title }).then(async (project) => {
              setCreateProjectOpen(false);
              await refreshProjects();
              await loadProject(project.id);
            }).catch((error) => {
              setLoadError(error instanceof Error ? error.message : "项目创建失败");
            });
          }}
        />
      </>
    );
  }

  return (
    <ProjectWorkspace
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
      onSaveProjectConfiguration={saveProjectConfiguration}
      onEnhancePrompt={(request) => gateway.enhancePrompt(currentProject.id, request)}
      onBatchEnhancePrompts={async (request) => {
        const response = await batchReviewGateway.batchEnhancePrompts(currentProject.id, request);
        await reloadCurrentProject();
        return response;
      }}
      onApprovePrompt={async (taskId) => {
        const result = await batchReviewGateway.approvePrompt(currentProject.id, taskId);
        await loadPromptReviewState(currentProject.id);
        return result;
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
