import type { StoryboardDomainSnapshot } from "../../domain/storyboard";

export type DirectorProject = {
  readOnly?: boolean;
  taskMissingReferences?: Record<string, boolean>;
  taskGenerationNotes?: Record<string, string | null>;
  taskWarnings?: Record<string, string[]>;
  taskNewResults?: Record<string, { video?: string | null; prompt?: string | null }>;
  automaticCoverUrl?: string;
  runtime?: import("../../gateways/projectGateway").ProjectWorkspaceView["runtime"];
  taskTimings?: Record<string, import("../../gateways/projectGateway").TaskTiming>;
  id: string;
  title: string;
  description: string;
  useDescriptionForAiPrompt: boolean;
  coverUrl?: string;
  coverAssetId?: string | null;
  snapshot: StoryboardDomainSnapshot;
};
