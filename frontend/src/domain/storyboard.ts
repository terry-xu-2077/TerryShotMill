export type EntityId = string;
export type IsoDateTime = string;
export type OrderKey = string;

export type Scene = {
  id: EntityId;
  number: string;
  title: string;
  summary: string;
  orderKey: OrderKey;
  location: string;
  timeOfDay: string;
  notes: string;
};

export type StoryboardFrameSourceType =
  | "placeholder"
  | "imported-image"
  | "asset"
  | "video-frame"
  | "result-frame";

export type StoryboardFrame = {
  sourceType: StoryboardFrameSourceType;
  sourceId?: EntityId;
  previewUrl?: string;
  frameTime?: number;
  updatedAt: IsoDateTime;
};

export type TaskVisualBeat = {
  id: EntityId;
  label: string;
  description: string;
  plannedStart?: number;
  plannedEnd?: number;
  shotSize?: string;
  cameraMovement?: string;
  notes?: string;
};

export type TaskAssetBinding = {
  assetId: EntityId;
  role: "character" | "scene" | "prop" | "reference" | "audio";
  reference?: string;
  notes?: string;
};

export type AssetMediaType = "image" | "video" | "audio";
export type AssetCategory = "character" | "scene" | "prop" | "reference";

export type ProjectAsset = {
  id: EntityId;
  name: string;
  mediaType: AssetMediaType;
  category: AssetCategory;
  projectRelativePath: string;
  mediaUrl?: string;
  previewUrl?: string;
  tags: string[];
  durationSeconds?: number;
  checksum: string;
  originalFilename?: string;
  sourceFile?: File;
  importSource?: { kind: "asset" | "result" | "archive"; id: string };
};

export type ResolvedTaskAssetSnapshot = Readonly<TaskAssetBinding & {
  mediaType: AssetMediaType;
  projectRelativePath: string;
  checksum: string;
}>;

export type GenerationTaskState =
  | "draft"
  | "prompt-generating"
  | "prompt-ready"
  | "ready"
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "blocked"
  | "context-stale";

export type GenerationProfileCapability = {
  multiShotPrompt: boolean;
  maxDurationSeconds?: number;
  continuation: boolean;
};

export type PromptRevision = {
  id: EntityId;
  revision: number;
  providerId: string;
  modelId: string;
  skillVersion: string;
  inputSnapshot: Readonly<Record<string, unknown>>;
  output: string;
  createdAt: IsoDateTime;
};

export type GenerationTask = {
  id: EntityId;
  number: string;
  title: string;
  summary: string;
  scriptSource: string;
  userIntent: string;
  storyboardFrame: StoryboardFrame;
  visualBeats: TaskVisualBeat[];
  assetBindings: TaskAssetBinding[];
  plannedDurationSeconds: number;
  generationProfileId: EntityId;
  generationProfileLabel: string;
  aiPrompt: string;
  finalPrompt: string;
  promptRevisions: PromptRevision[];
  generationParams: Record<string, unknown>;
  contextLinkIds: EntityId[];
  state: GenerationTaskState;
  progress?: number;
  jobIds: EntityId[];
  primaryResultId?: EntityId;
};

export type TaskStoryboardPlacement = {
  taskId: EntityId;
  sceneId: EntityId;
  orderKey: OrderKey;
};

export type TaskProposal = {
  tempId: EntityId;
  scriptExcerpt: string;
  title: string;
  summary: string;
  userIntent: string;
  visualBeats: TaskVisualBeat[];
  plannedDurationSeconds: number;
  suggestedAssetIds: EntityId[];
  suggestedProfileId: EntityId;
  suggestedProfileLabel: string;
  notes: string;
  targetSceneId: EntityId;
};

export type GenerationContextKind = "semantic" | "visual" | "audio" | "latent" | "native" | "fallback";

export type GenerationContextLink = {
  id: EntityId;
  sourceTaskId: EntityId;
  targetTaskId: EntityId;
  kind: GenerationContextKind;
  sourceResultId?: EntityId;
  stale: boolean;
};

export type TaskContentSnapshot = Readonly<{
  title: string;
  summary: string;
  scriptSource: string;
  userIntent: string;
  visualBeats: readonly Readonly<TaskVisualBeat>[];
  plannedDurationSeconds: number;
}>;

export type PromptStoryTaskContext = Readonly<{
  taskId: EntityId;
  number: string;
  title: string;
  summary: string;
  userIntent: string;
  primaryResultId?: EntityId;
}>;

export type PromptContextSource = Readonly<{
  link: Readonly<GenerationContextLink>;
  sourceTask: PromptStoryTaskContext;
  sourceResult?: Readonly<Pick<Result, "id" | "videoUrl" | "previewUrl" | "metadata" | "reviewState">>;
}>;

export type PromptRequest = Readonly<{
  taskId: EntityId;
  taskContent: TaskContentSnapshot;
  visualBeats: readonly Readonly<TaskVisualBeat>[];
  assets: readonly ResolvedTaskAssetSnapshot[];
  previousTaskContext: Readonly<{
    storyTask?: PromptStoryTaskContext;
    generationSources: readonly PromptContextSource[];
  }>;
  nextStoryContext?: PromptStoryTaskContext;
  targetGenerationProfile: Readonly<{
    id: EntityId;
    label: string;
    capability: Readonly<GenerationProfileCapability>;
  }>;
}>;

export type JobState = "queued" | "running" | "completed" | "failed" | "cancelled";

export type Job = Readonly<{
  id: EntityId;
  taskId: EntityId;
  providerId: EntityId;
  state: JobState;
  progress?: number;
  errorSummary?: string;
  taskContentSnapshot: TaskContentSnapshot;
  finalPromptSnapshot: string;
  assetsSnapshot: readonly ResolvedTaskAssetSnapshot[];
  generationProfileSnapshot: Readonly<{
    id: EntityId;
    capability: Readonly<GenerationProfileCapability>;
  }>;
  paramsSnapshot: Readonly<Record<string, unknown>>;
  contextSnapshot: readonly Readonly<GenerationContextLink>[];
  createdAt: IsoDateTime;
}>;

export type ResultReviewState = "pending" | "approved" | "rejected";

export type Result = {
  id: EntityId;
  jobId: EntityId;
  videoUrl: string;
  previewUrl?: string;
  metadata: Record<string, unknown>;
  reviewState: ResultReviewState;
};

export type StoryboardDomainSnapshot = {
  scenes: Scene[];
  assets: ProjectAsset[];
  tasks: GenerationTask[];
  taskPlacements: TaskStoryboardPlacement[];
  generationContextLinks: GenerationContextLink[];
  jobs: Job[];
  results: Result[];
};

export function listTasksInStoryOrder(snapshot: StoryboardDomainSnapshot, sceneId: EntityId) {
  const tasksById = new Map(snapshot.tasks.map((task) => [task.id, task]));
  return snapshot.taskPlacements
    .filter((placement) => placement.sceneId === sceneId)
    .slice()
    .sort((left, right) => left.orderKey.localeCompare(right.orderKey))
    .map((placement) => tasksById.get(placement.taskId))
    .filter((task): task is GenerationTask => Boolean(task));
}

export function getTaskPlacement(snapshot: StoryboardDomainSnapshot, taskId: EntityId) {
  return snapshot.taskPlacements.find((placement) => placement.taskId === taskId);
}

export function listContextForTask(snapshot: StoryboardDomainSnapshot, taskId: EntityId) {
  return snapshot.generationContextLinks.filter((link) => link.sourceTaskId === taskId || link.targetTaskId === taskId);
}

export function listResultsForTask(snapshot: StoryboardDomainSnapshot, taskId: EntityId) {
  const jobIds = new Set(snapshot.jobs.filter((job) => job.taskId === taskId).map((job) => job.id));
  return snapshot.results.filter((result) => jobIds.has(result.jobId));
}

export function resolveTaskAssetSnapshots(snapshot: StoryboardDomainSnapshot, taskId: EntityId): ResolvedTaskAssetSnapshot[] {
  const task = snapshot.tasks.find((item) => item.id === taskId);
  if (!task) return [];
  const assetsById = new Map(snapshot.assets.map((asset) => [asset.id, asset]));
  return task.assetBindings.flatMap((binding) => {
    const asset = assetsById.get(binding.assetId);
    if (!asset) return [];
    return [{
      ...binding,
      mediaType: asset.mediaType,
      projectRelativePath: asset.projectRelativePath,
      checksum: asset.checksum,
    }];
  });
}

function toPromptStoryTaskContext(task: GenerationTask): PromptStoryTaskContext {
  return {
    taskId: task.id,
    number: task.number,
    title: task.title,
    summary: task.summary,
    userIntent: task.userIntent,
    primaryResultId: task.primaryResultId,
  };
}

export function buildPromptRequest(
  snapshot: StoryboardDomainSnapshot,
  taskId: EntityId,
  targetGenerationProfile: PromptRequest["targetGenerationProfile"],
): PromptRequest {
  const task = snapshot.tasks.find((item) => item.id === taskId);
  if (!task) throw new Error(`Unknown GenerationTask: ${taskId}`);

  const orderedTasks = snapshot.scenes
    .slice()
    .sort((left, right) => left.orderKey.localeCompare(right.orderKey))
    .flatMap((scene) => listTasksInStoryOrder(snapshot, scene.id));
  const storyIndex = orderedTasks.findIndex((item) => item.id === taskId);
  const previousStoryTask = storyIndex > 0 ? orderedTasks[storyIndex - 1] : undefined;
  const nextStoryTask = storyIndex >= 0 ? orderedTasks[storyIndex + 1] : undefined;

  const generationSources = snapshot.generationContextLinks
    .filter((link) => link.targetTaskId === taskId)
    .flatMap((link): PromptContextSource[] => {
      const sourceTask = snapshot.tasks.find((item) => item.id === link.sourceTaskId);
      if (!sourceTask) return [];
      const sourceResult = link.sourceResultId
        ? snapshot.results.find((result) => result.id === link.sourceResultId)
        : undefined;
      return [{
        link: { ...link },
        sourceTask: toPromptStoryTaskContext(sourceTask),
        sourceResult: sourceResult ? {
          id: sourceResult.id,
          videoUrl: sourceResult.videoUrl,
          previewUrl: sourceResult.previewUrl,
          metadata: { ...sourceResult.metadata },
          reviewState: sourceResult.reviewState,
        } : undefined,
      }];
    });

  const visualBeats = task.visualBeats.map((beat) => ({ ...beat }));
  return {
    taskId: task.id,
    taskContent: {
      title: task.title,
      summary: task.summary,
      scriptSource: task.scriptSource,
      userIntent: task.userIntent,
      visualBeats,
      plannedDurationSeconds: task.plannedDurationSeconds,
    },
    visualBeats,
    assets: resolveTaskAssetSnapshots(snapshot, task.id),
    previousTaskContext: {
      storyTask: previousStoryTask ? toPromptStoryTaskContext(previousStoryTask) : undefined,
      generationSources,
    },
    nextStoryContext: nextStoryTask ? toPromptStoryTaskContext(nextStoryTask) : undefined,
    targetGenerationProfile: {
      id: targetGenerationProfile.id,
      label: targetGenerationProfile.label,
      capability: { ...targetGenerationProfile.capability },
    },
  };
}
