import { httpProjectGateway, projectRequest } from "./projectGateway";

export type PendingImportConfiguration = {
  taskId: string; title: string; revision: number; sourceConfigurationId: string | null;
};
export interface ImportConfigurationGateway {
  pending(projectId: string): Promise<PendingImportConfiguration[]>;
  options(): Promise<{ value: string; label: string }[]>;
  confirm(projectId: string, taskId: string, configurationId: string, revision: number): Promise<void>;
}
export const importConfigurationGateway: ImportConfigurationGateway = {
  pending: id => projectRequest(`/projects/${encodeURIComponent(id)}/import-configuration`),
  options: async () => {
    const settings = await httpProjectGateway.getApplicationSettings();
    return settings.comfyui.workflowProfiles.filter(profile => profile.enabled && profile.workflowFile)
      .map(profile => ({ value: profile.id, label: profile.name }));
  },
  confirm: (projectId, taskId, configurationId, revision) => projectRequest(
    `/projects/${encodeURIComponent(projectId)}/import-configuration/${encodeURIComponent(taskId)}/confirm`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ configurationId, revision }) },
  ),
};
