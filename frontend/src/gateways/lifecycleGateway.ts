import { projectRequest, type ProjectSummary, type ProjectWorkspaceView } from "./projectGateway";

export type LifecycleScope = "active" | "archived" | "trash";
export type LifecycleAction = "archive" | "unarchive" | "trash" | "restore";
export type LifecycleState = { id: string; archivedAt: string | null; deletedAt: string | null };
export type DeletionImpact = {
  sourceTaskId: string; sourceTaskTitle: string;
  targetTaskId: string; targetTaskTitle: string;
  kind: string; sourceResultId: string | null;
};
export type PermanentDeleteOutcome = {
  deletedIds: string[]; archivedResultCount: number; cleanupId: string;
};

export interface LifecycleGateway {
  listProjects(scope: LifecycleScope): Promise<ProjectSummary[]>;
  getWorkspace(projectId: string, scope: LifecycleScope): Promise<ProjectWorkspaceView>;
  transitionTasks(projectId: string, taskIds: string[], action: LifecycleAction): Promise<LifecycleState[]>;
  transitionProject(projectId: string, action: LifecycleAction): Promise<LifecycleState>;
  deletionPreview(projectId: string, taskIds: string[]): Promise<DeletionImpact[]>;
  purgeTasks(projectId: string, taskIds: string[], archiveResults: boolean): Promise<PermanentDeleteOutcome>;
  purgeProject(projectId: string, archiveResults: boolean): Promise<PermanentDeleteOutcome>;
}

const projectPath = (id: string) => `/projects/${encodeURIComponent(id)}`;
const post = <T>(path: string, body: unknown) => projectRequest<T>(path, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

export const lifecycleGateway: LifecycleGateway = {
  async listProjects(scope) {
    return (await projectRequest<{ items: ProjectSummary[] }>(`/projects?scope=${scope}`)).items;
  },
  getWorkspace: (id, scope) => projectRequest(`${projectPath(id)}/workspace?scope=${scope}`),
  transitionTasks: (id, taskIds, action) => post(`${projectPath(id)}/tasks/lifecycle`, { taskIds, action }),
  transitionProject: (id, action) => post(`${projectPath(id)}/lifecycle`, { action }),
  deletionPreview: (id, taskIds) => post(`${projectPath(id)}/tasks/deletion-preview`, { taskIds }),
  purgeTasks: (id, taskIds, archiveResults) => post(`${projectPath(id)}/tasks/permanent-delete`, {
    taskIds, archiveResults, confirmed: true,
  }),
  purgeProject: (id, archiveResults) => post(`${projectPath(id)}/permanent-delete`, {
    archiveResults, confirmed: true,
  }),
};
