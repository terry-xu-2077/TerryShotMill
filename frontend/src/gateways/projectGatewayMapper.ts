import type {
  GenerationTask,
  Job,
  PromptRevision,
  Result,
  StoryboardDomainSnapshot,
  TaskAssetBinding,
} from "../domain/storyboard";
import type { DirectorProject } from "../features/projects/projectTypes";
import type {
  ProjectSettings,
  ProjectWorkspaceView,
  PromptRevisionView,
  SaveTaskInput,
  TaskEditorView,
  TaskSummary,
} from "./projectGateway";

const sceneId = "scene-project-workspace";

function taskState(status: TaskSummary["status"], videoStatus?: string, promptStatus?: string): GenerationTask["state"] {
  if (videoStatus === "queued") return "queued";
  if (videoStatus === "running") return "running";
  if (promptStatus === "running") return "prompt-generating";
  if (status === "running") return "running";
  if (status === "completed") return "completed";
  if (status === "failed") return "failed";
  return "draft";
}

function taskRole(value?: string): TaskAssetBinding["role"] {
  if (value === "character" || value === "scene" || value === "prop" || value === "audio") {
    return value;
  }
  return "reference";
}

function summaryTask(summary: TaskSummary): GenerationTask {
  return {
    id: summary.id,
    number: `T01-${String(summary.displayNumber).padStart(3, "0")}`,
    title: summary.title,
    summary: summary.promptExcerpt,
    scriptSource: "",
    userIntent: summary.promptExcerpt,
    storyboardFrame: {
      sourceType: summary.previewUrl ? "result-frame" : "placeholder",
      previewUrl: summary.previewUrl,
      updatedAt: new Date(0).toISOString(),
    },
    visualBeats: [],
    assetBindings: Array.from({ length: summary.assetCount }, (_, index) => ({
      assetId: `summary:${summary.id}:${index}`,
      role: "reference" as const,
    })),
    plannedDurationSeconds: summary.durationSeconds,
    generationProfileId: "profile-h3-multi-shot",
    generationProfileLabel: "H3",
    aiPrompt: "",
    finalPrompt: summary.promptExcerpt,
    promptRevisions: [],
    generationParams: {
      resolution: summary.generationSummary.resolution,
      quality: summary.generationSummary.quality,
      generationMode: "全能参考",
      contextMode: "不承接",
      promptSource: summary.promptSource ?? "unknown",
      resultCount: summary.resultCount,
    },
    contextLinkIds: [],
    state: taskState(summary.status, summary.videoGenerationStatus, summary.promptEnhancementStatus),
    progress: summary.progress,
    jobIds: Array.from({ length: summary.resultCount }, (_, index) => `summary-job:${summary.id}:${index}`),
    primaryResultId: summary.primaryResult?.id,
  };
}

function summaryHistory(workspace: ProjectWorkspaceView): { jobs: Job[]; results: Result[] } {
  const jobs: Job[] = [];
  const results: Result[] = [];
  for (const task of workspace.tasks) {
    for (let index = 0; index < task.resultCount; index += 1) {
      const jobId = `summary-job:${task.id}:${index}`;
      jobs.push({
        id: jobId,
        taskId: task.id,
        providerId: "read-model",
        state: "completed",
        taskContentSnapshot: {
          title: task.title,
          summary: task.promptExcerpt,
          scriptSource: "",
          userIntent: task.promptExcerpt,
          visualBeats: [],
          plannedDurationSeconds: task.durationSeconds,
        },
        finalPromptSnapshot: task.promptExcerpt,
        assetsSnapshot: [],
        generationProfileSnapshot: {
          id: "read-model",
          capability: { multiShotPrompt: true, continuation: true },
        },
        paramsSnapshot: {},
        contextSnapshot: [],
        createdAt: new Date(0).toISOString(),
      });
      const primary = index === 0 ? task.primaryResult : undefined;
      results.push({
        id: primary?.id ?? `summary-result:${task.id}:${index}`,
        jobId,
        videoUrl: primary?.videoUrl ?? "",
        previewUrl: primary?.previewUrl,
        metadata: { durationSeconds: primary?.durationSeconds },
        reviewState: "pending",
      });
    }
  }
  return { jobs, results };
}

export function mapWorkspaceProject(
  settings: ProjectSettings,
  workspace: ProjectWorkspaceView,
  assets: DirectorProject["snapshot"]["assets"],
): DirectorProject {
  const history = summaryHistory(workspace);
  return {
    id: settings.id,
    title: settings.title,
    description: settings.description,
    useDescriptionForAiPrompt: settings.useDescriptionForAiPrompt,
    coverAssetId: settings.coverAssetId,
    coverUrl: settings.coverUrl,
    automaticCoverUrl: settings.automaticCoverUrl,
    runtime: workspace.runtime,
    taskTimings: Object.fromEntries(workspace.tasks.filter((task) => task.timing).map((task) => [task.id, task.timing!])),
    taskNewResults: Object.fromEntries(workspace.tasks.map(task => [task.id, { video: task.latestVideoResultId, prompt: task.latestPromptRevisionId }])),
    taskGenerationNotes: Object.fromEntries(workspace.tasks.map(task => [task.id, task.generationStatusNote ?? null])),
    taskWarnings: Object.fromEntries(workspace.tasks.map(task => [task.id, task.generationWarnings ?? []])),
    snapshot: {
      scenes: [{
        id: sceneId,
        number: "S01",
        title: settings.title,
        summary: settings.description,
        orderKey: "0001",
        location: "",
        timeOfDay: "",
        notes: "",
      }],
      assets,
      tasks: workspace.tasks.map(summaryTask),
      taskPlacements: workspace.tasks.map((task, index) => ({
        taskId: task.id,
        sceneId,
        orderKey: String(index + 1).padStart(6, "0"),
      })),
      generationContextLinks: [],
      jobs: history.jobs,
      results: history.results,
    },
  };
}

function promptRevision(value: PromptRevisionView, index: number): PromptRevision {
  return {
    id: value.id,
    revision: index + 1,
    providerId: value.providerId ?? "",
    modelId: value.modelId ?? "",
    skillVersion: value.skillVersion,
    inputSnapshot: {
      sourceUserPrompt: value.sourceUserPrompt,
      assetIds: value.assetIds,
      includeProjectBackground: value.includeProjectBackground,
      includePreviousTaskSummary: value.includePreviousTaskSummary,
      previousTaskSummarySnapshot: value.previousTaskSummarySnapshot,
      targetSkill: value.targetSkill,
    },
    output: value.prompt,
    createdAt: value.createdAt,
  };
}

export function mapTaskEditor(
  view: TaskEditorView,
  revisions: PromptRevisionView[],
  fallback?: GenerationTask,
): GenerationTask {
  const chronologicalRevisions = [...revisions].sort((a, b) => Date.parse(a.createdAt) - Date.parse(b.createdAt));
  const history = chronologicalRevisions.map((revision) => ({
    id: revision.id,
    createdAt: revision.createdAt,
    prompt: revision.prompt,
    sourceUserPrompt: revision.sourceUserPrompt,
    previousTaskSummary: revision.previousTaskSummarySnapshot,
    projectBackgroundUsed: revision.includeProjectBackground,
  }));
  let selectedHistory = [...history].reverse().find((item) => item.prompt === view.aiEnhancedPrompt);
  // The saved task may contain human edits that are not an immutable AI revision.
  if (!selectedHistory && view.aiEnhancedPrompt.trim()) {
    selectedHistory = {
      id: `saved-${view.id}`, createdAt: "", prompt: view.aiEnhancedPrompt,
      sourceUserPrompt: view.userPrompt, previousTaskSummary: undefined, projectBackgroundUsed: false,
    };
    history.push(selectedHistory);
  }
  return {
    id: view.id,
    number: `T01-${String(view.displayNumber).padStart(3, "0")}`,
    title: view.title,
    summary: view.summary,
    scriptSource: view.scriptSource,
    userIntent: view.userIntent,
    storyboardFrame: fallback?.storyboardFrame ?? {
      sourceType: "placeholder",
      updatedAt: new Date(0).toISOString(),
    },
    visualBeats: [],
    assetBindings: view.assetBindings.map((binding) => ({
      assetId: binding.assetId,
      role: taskRole(binding.role),
      reference: binding.reference,
      notes: binding.role,
    })),
    plannedDurationSeconds: view.durationSeconds,
    generationProfileId: "profile-h3-multi-shot",
    generationProfileLabel: "H3",
    aiPrompt: view.aiEnhancedPrompt,
    finalPrompt: view.finalPrompt,
    promptRevisions: revisions.map(promptRevision),
    generationParams: {
      resolution: view.generation.resolution,
      workflowProfileId: view.generation.workflowProfileId,
      workflowInputs: view.generation.workflowInputs,
      quality: view.generation.quality,
      generationMode: view.generation.mode,
      contextMode: view.generation.contextMode,
      contextStartSeconds: view.generation.contextStartSeconds,
      contextEndSeconds: view.generation.contextEndSeconds,
      contextDurationSeconds: view.generation.contextDurationSeconds,
      promptSource: view.promptSource,
      userPrompt: view.userPrompt,
      userPromptHistory: view.userPromptHistory ?? [],
      userPromptViewMode: view.editorPreference.userViewMode,
      aiPromptViewMode: view.editorPreference.aiViewMode,
      revision: view.revision,
      previousTaskDurationSeconds: view.previousTaskDurationSeconds,
      aiPromptHistory: history,
      selectedAiPromptHistoryId: selectedHistory?.id ?? history.at(-1)?.id,
    },
    contextLinkIds: [],
    state: fallback?.state ?? (view.finalPrompt.trim() ? "ready" : "draft"),
    progress: fallback?.progress,
    jobIds: fallback?.jobIds ?? [],
    primaryResultId: fallback?.primaryResultId,
  };
}

export function taskSaveInput(task: GenerationTask): SaveTaskInput {
  const params = task.generationParams;
  const promptSource = params.promptSource === "ai" ? "ai" : "user";
  return {
    title: task.title,
    summary: task.summary,
    scriptSource: task.scriptSource,
    userIntent: task.userIntent,
    saveUserPromptVersion: params.saveUserPromptVersion === true,
    userPrompt: typeof params.userPrompt === "string" ? params.userPrompt : task.userIntent,
    aiEnhancedPrompt: task.aiPrompt,
    promptSource,
    durationSeconds: task.plannedDurationSeconds,
    generation: {
      resolution: typeof params.resolution === "string" ? params.resolution : "1080p",
      workflowProfileId: typeof params.workflowProfileId === "string" ? params.workflowProfileId : undefined,
      workflowInputs: params.workflowInputs as import("./projectGateway").WorkflowInputSelection | undefined,
      quality: typeof params.quality === "string" ? params.quality : "标准",
      mode: typeof params.generationMode === "string" ? params.generationMode : "全能参考",
      contextMode: typeof params.contextMode === "string" ? params.contextMode : "不承接",
      contextStartSeconds: typeof params.contextStartSeconds === "number" ? params.contextStartSeconds : undefined,
      contextEndSeconds: typeof params.contextEndSeconds === "number" ? params.contextEndSeconds : undefined,
      contextDurationSeconds: typeof params.contextDurationSeconds === "number" ? params.contextDurationSeconds : undefined,
    },
    assetBindings: task.assetBindings
      .filter((binding) => !binding.assetId.startsWith("summary:"))
      .map((binding, index) => ({
        assetId: binding.assetId,
        reference: binding.reference ?? `<Picture ${index + 1}>`,
        role: binding.notes ?? binding.role,
      })),
    editorPreference: {
      userViewMode: params.userPromptViewMode === "text" ? "text" : "visual",
      aiViewMode: params.aiPromptViewMode === "text" ? "text" : "visual",
    },
    revision: typeof params.revision === "number" ? params.revision : undefined,
  };
}

export function replaceTask(
  snapshot: StoryboardDomainSnapshot,
  task: GenerationTask,
): StoryboardDomainSnapshot {
  return {
    ...snapshot,
    tasks: snapshot.tasks.map((item) => item.id === task.id ? task : item),
  };
}
