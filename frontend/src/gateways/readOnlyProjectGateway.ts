import { httpProjectGateway, projectRequest, type TaskEditorView } from "./projectGateway";
import type { ProjectAsset } from "../domain/storyboard";

export type HistoricalResult = { id: string; videoUrl: string; previewUrl: string | null; createdAt: string };
export interface ReadOnlyProjectGateway {
  assets(projectId: string): Promise<ProjectAsset[]>;
  task(projectId: string, taskId: string): Promise<TaskEditorView>;
  results(projectId: string, taskId: string): Promise<HistoricalResult[]>;
}
export const readOnlyProjectGateway: ReadOnlyProjectGateway = {
  assets: id => httpProjectGateway.listAssets(id),
  task: (id, task) => httpProjectGateway.getTaskEditor(id, task),
  async results(id, task) {
    return (await projectRequest<{ items: HistoricalResult[] }>(`/projects/${encodeURIComponent(id)}/tasks/${encodeURIComponent(task)}/results`)).items;
  },
};
