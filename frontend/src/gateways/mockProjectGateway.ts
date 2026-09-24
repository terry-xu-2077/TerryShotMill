import type { DirectorProject } from "../components/project/projectTypes";
import systemPromptPresets from "../components/settings/systemPromptPresets.json";
import { listTasksInStoryOrder, type GenerationTask } from "../domain/storyboard";
import { makeEmptyProject, makeMockProjects } from "../mock/projects";
import type { PromptEnhancementRequest } from "../services/promptEnhancement";
import { insertTaskAfter, updateTaskComposerFields } from "../components/task/storyboardMutations";
import type {
  AssetPatch,
  ApplicationSettings,
  BatchPromptEnhancementRequest,
  BatchPromptEnhancementResponse,
  ComfyUIWorkflow,
  ProjectGateway,
  ProjectSettings,
  ProjectStatus,
  ProjectSummary,
  ProjectWorkspaceView,
  PromptRevisionView,
  SaveTaskInput,
  TaskEditorView,
  TaskSummary,
} from "./projectGateway";

const DEFAULT_APPLICATION_SETTINGS: ApplicationSettings = {
  promptAiLabel: "演示增强服务",
  providerMode: "local",
  systemPrompt: systemPromptPresets[0].prompt,
  systemPromptPresets,
  apiBaseUrl: "",
  apiModel: "",
  apiKey: "",
  apiSupportsNativeVideo: false,
  localInference: {
    presetPrompt: "Empty - Nothing",
    inferenceMode: "images",
    maxFrames: 24,
    maxSize: 256,
    seedMode: "randomize",
    seed: 0,
    forceOffload: false,
    saveStates: false,
  },
  comfyui: {
    baseUrl: "http://127.0.0.1:8188",
    rootPath: "",
    workflowDirectory: "user/default/workflows",
    defaultProfileId: "",
    workflowProfiles: [],
  },
};

function orderedTasks(project: DirectorProject) {
  return project.snapshot.scenes
    .slice()
    .sort((left, right) => left.orderKey.localeCompare(right.orderKey))
    .flatMap((scene) => listTasksInStoryOrder(project.snapshot, scene.id));
}

function status(project: DirectorProject): ProjectStatus {
  const states = project.snapshot.tasks.map((task) => task.state);
  if (states.some((value) => value === "running" || value === "queued")) return "running";
  if (states.length && states.every((value) => value === "completed")) return "completed";
  if (states.includes("failed")) return "failed";
  return "idle";
}

function taskStatus(task: GenerationTask): TaskSummary["status"] {
  if (task.state === "running" || task.state === "queued") return "running";
  if (task.state === "completed") return "completed";
  if (task.state === "failed") return "failed";
  return "idle";
}

function taskSummary(project: DirectorProject, task: GenerationTask, index: number): TaskSummary {
  const jobIds = new Set(project.snapshot.jobs.filter((job) => job.taskId === task.id).map((job) => job.id));
  const results = project.snapshot.results.filter((result) => jobIds.has(result.jobId));
  const primary = results.find((result) => result.id === task.primaryResultId);
  return {
    id: task.id,
    displayNumber: index + 1,
    title: task.title,
    promptExcerpt: task.finalPrompt || task.userIntent || task.summary,
    previewUrl: primary?.previewUrl ?? task.storyboardFrame.previewUrl,
    status: taskStatus(task),
    progress: task.progress,
    assetCount: task.assetBindings.length,
    resultCount: results.length,
    durationSeconds: task.plannedDurationSeconds,
    generationSummary: {
      resolution: String(task.generationParams.resolution ?? "1080p"),
      quality: String(task.generationParams.quality ?? "标准"),
    },
    primaryResult: primary ? {
      id: primary.id,
      previewUrl: primary.previewUrl,
      videoUrl: primary.videoUrl,
    } : undefined,
  };
}

function summary(project: DirectorProject): ProjectSummary {
  return {
    id: project.id,
    title: project.title,
    status: status(project),
    coverUrl: project.coverUrl,
    taskCount: project.snapshot.tasks.length,
    assetCount: project.snapshot.assets.length,
    updatedAt: new Date().toISOString(),
  };
}

function editorView(task: GenerationTask, index: number, previous?: GenerationTask): TaskEditorView {
  const params = task.generationParams;
  return {
    id: task.id,
    displayNumber: index + 1,
    title: task.title,
    summary: task.summary,
    scriptSource: task.scriptSource,
    userIntent: task.userIntent,
    promptSource: params.promptSource === "ai" ? "ai" : "user",
    userPrompt: typeof params.userPrompt === "string" ? params.userPrompt : task.finalPrompt,
    aiEnhancedPrompt: task.aiPrompt,
    finalPrompt: task.finalPrompt,
    editorPreference: {
      userViewMode: params.userPromptViewMode === "text" ? "text" : "visual",
      aiViewMode: params.aiPromptViewMode === "text" ? "text" : "visual",
    },
    durationSeconds: task.plannedDurationSeconds,
    previousTaskDurationSeconds: previous?.plannedDurationSeconds,
    generation: {
      resolution: String(params.resolution ?? "1080p"),
      workflowProfileId: typeof params.workflowProfileId === "string" ? params.workflowProfileId : undefined,
      quality: String(params.quality ?? "标准"),
      mode: String(params.generationMode ?? "全能参考"),
      contextMode: String(params.contextMode ?? "不承接"),
      contextStartSeconds: typeof params.contextStartSeconds === "number" ? params.contextStartSeconds : undefined,
      contextEndSeconds: typeof params.contextEndSeconds === "number" ? params.contextEndSeconds : undefined,
      contextDurationSeconds: typeof params.contextDurationSeconds === "number" ? params.contextDurationSeconds : undefined,
    },
    assetBindings: task.assetBindings.map((binding, bindingIndex) => ({
      assetId: binding.assetId,
      reference: binding.reference ?? `<Picture ${bindingIndex + 1}>`,
      role: binding.role,
    })),
    revision: typeof params.revision === "number" ? params.revision : 1,
  };
}

function taskFromInput(id: string, number: number, input: SaveTaskInput): GenerationTask {
  return {
    id,
    number: `T01-${String(number).padStart(3, "0")}`,
    title: input.title,
    summary: input.summary,
    scriptSource: input.scriptSource,
    userIntent: input.userIntent,
    storyboardFrame: { sourceType: "placeholder", updatedAt: new Date().toISOString() },
    visualBeats: [],
    assetBindings: input.assetBindings.map((binding) => ({
      assetId: binding.assetId,
      role: binding.role === "character" || binding.role === "scene" || binding.role === "prop" || binding.role === "audio"
        ? binding.role
        : "reference",
      reference: binding.reference,
    })),
    plannedDurationSeconds: input.durationSeconds,
    generationProfileId: "profile-h3-multi-shot",
    generationProfileLabel: "H3",
    aiPrompt: input.aiEnhancedPrompt,
    finalPrompt: input.promptSource === "ai" ? input.aiEnhancedPrompt : input.userPrompt,
    promptRevisions: [],
    generationParams: {
      resolution: input.generation.resolution,
      workflowProfileId: input.generation.workflowProfileId,
      quality: input.generation.quality,
      generationMode: input.generation.mode,
      contextMode: input.generation.contextMode,
      contextStartSeconds: input.generation.contextStartSeconds,
      contextEndSeconds: input.generation.contextEndSeconds,
      contextDurationSeconds: input.generation.contextDurationSeconds,
      promptSource: input.promptSource,
      userPrompt: input.userPrompt,
      userPromptViewMode: input.editorPreference.userViewMode,
      aiPromptViewMode: input.editorPreference.aiViewMode,
      revision: (input.revision ?? 0) + 1,
    },
    contextLinkIds: [],
    state: input.userPrompt || input.aiEnhancedPrompt ? "ready" : "draft",
    jobIds: [],
  };
}

export class MockProjectGateway implements ProjectGateway {
  async getComfyUIStatus() {
    return { connected: false, bridgeNodeAvailable: false, baseUrl: "", message: "测试数据，未连接真实 Bridge。" };
  }
  private projects: DirectorProject[];
  private applicationSettings: ApplicationSettings = structuredClone(DEFAULT_APPLICATION_SETTINGS);

  constructor(projects = makeMockProjects()) {
    this.projects = structuredClone(projects);
  }

  private project(projectId: string) {
    const project = this.projects.find((item) => item.id === projectId);
    if (!project) throw new Error(`Unknown project: ${projectId}`);
    return project;
  }

  async getApplicationSettings() {
    return structuredClone(this.applicationSettings);
  }

  async updateApplicationSettings(input: ApplicationSettings) {
    this.applicationSettings = structuredClone(input);
    return structuredClone(this.applicationSettings);
  }

  async listComfyUIWorkflows(): Promise<ComfyUIWorkflow[]> {
    return [];
  }

  async getGlobalRuntime() {
    return Promise.all(this.projects.map(async project => {
      const view = await this.getWorkspace(project.id);
      return { project: view.project, runtime: view.runtime };
    }));
  }

  async listProjects() {
    return this.projects.map(summary);
  }

  async createProject(input: { title: string }) {
    const project = makeEmptyProject(input.title);
    this.projects.push(project);
    return summary(project);
  }

  async updateProject(projectId: string, input: Partial<ProjectSettings>) {
    const project = this.project(projectId);
    if (typeof input.title === "string") project.title = input.title;
    if (typeof input.description === "string") project.description = input.description;
    if (typeof input.useDescriptionForAiPrompt === "boolean") {
      project.useDescriptionForAiPrompt = input.useDescriptionForAiPrompt;
    }
    return summary(project);
  }

  async getProjectSettings(projectId: string) {
    const project = this.project(projectId);
    return {
      id: project.id,
      title: project.title,
      description: project.description,
      useDescriptionForAiPrompt: project.useDescriptionForAiPrompt,
    };
  }

  async getWorkspace(projectId: string): Promise<ProjectWorkspaceView> {
    const project = this.project(projectId);
    const tasks = orderedTasks(project);
    const running = tasks.find((task) => task.state === "running" || task.state === "queued");
    return {
      project: { id: project.id, title: project.title },
      tasks: tasks.map((task, index) => taskSummary(project, task, index)),
      runtime: {
        activeTaskId: running?.id,
        activeTaskTitle: running?.title,
        state: running?.state === "queued" ? "queued" : running ? "running" : "idle",
        progress: running?.progress,
        videoJobs: tasks.filter(task => task.state === "running" || task.state === "queued").map(task => ({ id: `mock-job-${task.id}`, taskId: task.id, title: task.title, state: task.state === "running" ? "running" as const : "queued" as const })),
      },
    };
  }

  async getTaskEditor(projectId: string, taskId: string) {
    const tasks = orderedTasks(this.project(projectId));
    const index = tasks.findIndex((task) => task.id === taskId);
    if (index < 0) throw new Error(`Unknown task: ${taskId}`);
    return editorView(tasks[index], index, tasks[index - 1]);
  }

  async updateEditorPreference(projectId: string, taskId: string, input: Partial<TaskEditorView["editorPreference"]>) {
    const task = this.project(projectId).snapshot.tasks.find((item) => item.id === taskId);
    if (!task) throw new Error(`Unknown task: ${taskId}`);
    task.generationParams = { ...task.generationParams,
      ...(input.userViewMode ? { userPromptViewMode: input.userViewMode } : {}),
      ...(input.aiViewMode ? { aiPromptViewMode: input.aiViewMode } : {}),
    };
    return (await this.getTaskEditor(projectId, taskId)).editorPreference;
  }

  async createTask(projectId: string, input: SaveTaskInput) {
    const project = this.project(projectId);
    const task = taskFromInput(`task-${Date.now()}`, project.snapshot.tasks.length + 1, input);
    const firstScene = project.snapshot.scenes[0];
    if (!firstScene) throw new Error("Project has no scene");
    project.snapshot = insertTaskAfter(project.snapshot, task, firstScene.id);
    return taskSummary(project, task, project.snapshot.tasks.length - 1);
  }

  async updateTask(projectId: string, taskId: string, input: SaveTaskInput) {
    const project = this.project(projectId);
    const replacement = taskFromInput(taskId, 1, input);
    const current = project.snapshot.tasks.find((task) => task.id === taskId);
    if (!current) throw new Error(`Unknown task: ${taskId}`);
    project.snapshot = updateTaskComposerFields(project.snapshot, taskId, {
      aiPrompt: replacement.aiPrompt,
      finalPrompt: replacement.finalPrompt,
      generationParams: replacement.generationParams,
    });
    project.snapshot = {
      ...project.snapshot,
      tasks: project.snapshot.tasks.map((task) => task.id === taskId ? {
        ...task,
        title: replacement.title,
        summary: replacement.summary,
        scriptSource: replacement.scriptSource,
        userIntent: replacement.userIntent,
        assetBindings: replacement.assetBindings,
        plannedDurationSeconds: replacement.plannedDurationSeconds,
      } : task),
    };
    const tasks = orderedTasks(project);
    const updated = tasks.find((task) => task.id === taskId)!;
    return taskSummary(project, updated, tasks.indexOf(updated));
  }

  async listAssets(projectId: string) {
    return structuredClone(this.project(projectId).snapshot.assets);
  }

  async importAsset(projectId: string, file: File, input: AssetPatch) {
    const asset = {
      id: `asset-${Date.now()}`,
      ...input,
      mediaType: file.type.startsWith("video/") ? "video" as const : file.type.startsWith("audio/") ? "audio" as const : "image" as const,
      projectRelativePath: file.name,
      previewUrl: file.type.startsWith("audio/") ? undefined : URL.createObjectURL(file),
      checksum: `mock-${file.size}-${file.lastModified}`,
      originalFilename: file.name,
    };
    this.project(projectId).snapshot.assets.push(asset);
    return asset;
  }

  async updateAsset(projectId: string, assetId: string, input: AssetPatch) {
    const assets = this.project(projectId).snapshot.assets;
    const index = assets.findIndex((asset) => asset.id === assetId);
    if (index < 0) throw new Error(`Unknown asset: ${assetId}`);
    assets[index] = { ...assets[index], ...input };
    return assets[index];
  }

  async deleteAsset(projectId: string, assetId: string) {
    const project = this.project(projectId);
    project.snapshot.assets = project.snapshot.assets.filter((asset) => asset.id !== assetId);
  }

  async listPromptRevisions(projectId: string, taskId: string): Promise<PromptRevisionView[]> {
    const task = this.project(projectId).snapshot.tasks.find((item) => item.id === taskId);
    return (task?.promptRevisions ?? []).map((revision) => ({
      id: revision.id,
      taskId,
      createdAt: revision.createdAt,
      prompt: revision.output,
      sourceUserPrompt: String(revision.inputSnapshot.sourceUserPrompt ?? ""),
      assetIds: [],
      includeProjectBackground: revision.inputSnapshot.includeProjectBackground === true,
      includePreviousTaskSummary: revision.inputSnapshot.includePreviousTaskSummary === true,
      targetSkill: "minimax-h3",
      skillVersion: revision.skillVersion,
      providerId: revision.providerId,
      modelId: revision.modelId,
    }));
  }

  async enhancePrompt(projectId: string, input: PromptEnhancementRequest) {
    const task = input.isDraft
      ? undefined
      : this.project(projectId).snapshot.tasks.find((item) => item.id === input.taskId);
    const taskRevision = task
      ? (typeof task.generationParams.revision === "number" ? task.generationParams.revision : 1) + 1
      : undefined;
    if (task && typeof taskRevision === "number") {
      task.aiPrompt = input.userPrompt;
      task.generationParams = { ...task.generationParams, revision: taskRevision };
    }
    return {
      id: `dev-ai-${Date.now()}`,
      createdAt: new Date().toISOString(),
      prompt: input.userPrompt,
      taskRevision,
    };
  }

  async batchEnhancePrompts(
    projectId: string,
    input: BatchPromptEnhancementRequest,
  ): Promise<BatchPromptEnhancementResponse> {
    const project = this.project(projectId);
    const items = input.taskIds.map((taskId) => {
      const task = project.snapshot.tasks.find((item) => item.id === taskId);
      if (!task) return { taskId, state: "failed" as const, error: "TASK_NOT_FOUND" };
      task.aiPrompt = task.userIntent || task.finalPrompt || task.summary;
      task.finalPrompt = task.aiPrompt;
      task.generationParams = {
        ...task.generationParams,
        promptSource: "ai",
        revision: (typeof task.generationParams.revision === "number" ? task.generationParams.revision : 1) + 1,
      };
      return { taskId, state: "completed" as const, revisionId: `mock-${Date.now()}-${taskId}` };
    });
    return {
      batchId: `mock-batch-${Date.now()}`,
      state: items.every((item) => item.state === "completed") ? "completed" : "partial",
      items,
    };
  }

  subscribeProject() {
    return () => undefined;
  }
}
