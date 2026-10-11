import { projectApiUrl, projectRequest } from "./projectGateway";

export type ProjectProviderRequirement = {
  kind: "video" | "prompt";
  requiresConfiguration: true;
  providerId?: string;
  workflowId?: string;
  workflowProfileId?: string;
  modelId?: string;
};

export type ProjectImportOutcome = {
  projectId: string;
  providerRequirements: ProjectProviderRequirement[];
};

export interface ProjectTransferGateway {
  prepareExport(projectId: string): Promise<{ token: string; expiresInSeconds: number }>;
  downloadUrl(token: string): string;
  discardExport(token: string): Promise<void>;
  exportUrl(projectId: string): string;
  importPackage(file: File, path: string, signal?: AbortSignal): Promise<ProjectImportOutcome>;
}

export const projectTransferGateway: ProjectTransferGateway = {
  prepareExport: id => projectRequest(`/projects/${encodeURIComponent(id)}/exports`, { method: "POST" }),
  downloadUrl: token => projectApiUrl(`/projects/exports/${encodeURIComponent(token)}`),
  discardExport: token => projectRequest(`/projects/exports/${encodeURIComponent(token)}`, { method: "DELETE" }),
  // Let the browser stream the attachment; do not buffer a video project ZIP
  // into a JS Blob, which can consume multiple gigabytes of renderer memory.
  exportUrl: id => projectApiUrl(`/projects/${encodeURIComponent(id)}/export`),
  importPackage(file, path, signal) {
    const body = new FormData();
    body.append("file", file);
    body.append("path", path);
    // The browser owns the multipart boundary. Imports are not auto-retried:
    // a lost response does not prove the server rolled back publication.
    return projectRequest<ProjectImportOutcome>("/projects/import", {
      method: "POST", body, signal,
    });
  },
};
