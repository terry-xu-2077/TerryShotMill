import { projectRequest, type ProjectSummary, type ProjectWorkspaceView } from "./projectGateway";

export type DeletionImpact = {
  sourceTaskId: string; sourceTaskTitle: string;
  targetTaskId: string; targetTaskTitle: string;
  kind: string; sourceResultId: string | null;
};

export interface LifecycleGateway {
  listProjects(): Promise<ProjectSummary[]>;
  getWorkspace(projectId: string): Promise<ProjectWorkspaceView>;
  deletionPreview(projectId: string, taskIds: string[]): Promise<DeletionImpact[]>;
  deleteTasks(projectId: string, taskIds: string[]): Promise<{ deletedIds: string[] }>;
  removeProject(projectId: string): Promise<void>;
}

const projectPath = (id: string) => `/projects/${encodeURIComponent(id)}`;
const post = <T>(path: string, body: unknown) => projectRequest<T>(path, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

export const lifecycleGateway: LifecycleGateway = {
  async listProjects() {
    return (await projectRequest<{ items: ProjectSummary[] }>("/projects")).items;
  },
  getWorkspace: id => projectRequest(`${projectPath(id)}/workspace`),
  deletionPreview: (id, taskIds) => post(`${projectPath(id)}/tasks/deletion-preview`, { taskIds }),
  deleteTasks: (id, taskIds) => post(`${projectPath(id)}/tasks/delete`, { taskIds }),
  removeProject: id => projectRequest(`${projectPath(id)}`, { method: "DELETE" }),
};
