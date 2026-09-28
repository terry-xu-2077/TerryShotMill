import { projectRequest, mapAsset, type BackendAsset } from "./projectGateway";
import type { ProjectAsset } from "../domain/storyboard";

export type ImportSource = { kind: "asset" | "result" | "archive"; id: string };
export type ImportCandidate = ImportSource & {
  name: string; sourceProjectId: string; sourceProjectTitle: string;
  mediaType: "image" | "video" | "audio"; previewUrl: string | null; createdAt: string;
};
export interface AssetTransferGateway {
  candidates(projectId: string): Promise<ImportCandidate[]>;
  importSources(projectId: string, sources: ImportSource[]): Promise<ProjectAsset[]>;
}
export const assetTransferGateway: AssetTransferGateway = {
  candidates: id => projectRequest(`/projects/${encodeURIComponent(id)}/assets/import-sources`),
  async importSources(id, sources) {
    const assets = await projectRequest<BackendAsset[]>(`/projects/${encodeURIComponent(id)}/assets/import`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sources }),
    });
    return assets.map(asset => mapAsset(id, asset));
  },
};
