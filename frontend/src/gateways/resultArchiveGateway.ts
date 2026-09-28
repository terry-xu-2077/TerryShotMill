import { projectRequest } from "./projectGateway";

export type ArchivedFile = { role: string; filename: string; size: number; url: string };
export type ArchivedResult = {
  id: string; sourceProjectId: string; sourceProjectTitle: string;
  sourceTaskId: string; sourceTaskTitle: string; generatedAt: string; archivedAt: string;
  finalPrompt: string; params: Record<string, unknown>; files: ArchivedFile[];
};
export interface ResultArchiveGateway {
  list(): Promise<ArchivedResult[]>;
  delete(archiveId: string): Promise<void>;
  importInto(projectId: string, archiveId: string): Promise<void>;
}
export const resultArchiveGateway: ResultArchiveGateway = {
  list: () => projectRequest("/result-archive"),
  delete: (archiveId) => projectRequest(`/result-archive/${encodeURIComponent(archiveId)}`, {
    method: "DELETE",
  }),
  async importInto(projectId, archiveId) {
    await projectRequest(`/projects/${encodeURIComponent(projectId)}/assets/import`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sources: [{ kind: "archive", id: archiveId }] }),
    });
  },
};
