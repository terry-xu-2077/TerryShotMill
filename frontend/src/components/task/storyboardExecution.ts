import {
  listTasksInStoryOrder,
  resolveTaskAssetSnapshots,
  type GenerationProfileCapability,
  type GenerationTask,
  type Job,
  type StoryboardDomainSnapshot,
} from "../../domain/storyboard";

export type GenerationProfileInput = {
  id: string;
  label: string;
  capability: GenerationProfileCapability;
};

export type ReadyValidationIssue = {
  code: "final-prompt" | "asset" | "profile" | "duration" | "visual-beat" | "context" | "provider";
  message: string;
};

function hasValidBeatTiming(task: GenerationTask) {
  let previousEnd = 0;
  return task.visualBeats.every((beat) => {
    const start = beat.plannedStart;
    const end = beat.plannedEnd;
    const valid = typeof start === "number"
      && typeof end === "number"
      && start >= previousEnd
      && end > start
      && end <= task.plannedDurationSeconds;
    if (valid) previousEnd = end;
    return valid;
  });
}

export function validateTaskReadiness(
  snapshot: StoryboardDomainSnapshot,
  taskId: string,
  profile: GenerationProfileInput,
  providerOnline: boolean,
): ReadyValidationIssue[] {
  const task = snapshot.tasks.find((item) => item.id === taskId);
  if (!task) return [{ code: "final-prompt", message: "Task 不存在。" }];

  const issues: ReadyValidationIssue[] = [];
  if (!task.finalPrompt.trim()) issues.push({ code: "final-prompt", message: "需要确认 Final Prompt。" });
  if (resolveTaskAssetSnapshots(snapshot, taskId).length !== task.assetBindings.length) {
    issues.push({ code: "asset", message: "存在无法解析的 asset_id。" });
  }
  if (task.visualBeats.length > 1 && !profile.capability.multiShotPrompt) {
    issues.push({ code: "profile", message: "当前 Profile 不支持多镜头提示词。" });
  }
  if (task.plannedDurationSeconds <= 0) {
    issues.push({ code: "duration", message: "Task 计划时长必须大于 0。" });
  } else if (profile.capability.maxDurationSeconds && task.plannedDurationSeconds > profile.capability.maxDurationSeconds) {
    issues.push({ code: "duration", message: `Task 计划时长超过 Profile 上限 ${profile.capability.maxDurationSeconds}s。` });
  }
  if (task.visualBeats.length > 0 && !hasValidBeatTiming(task)) {
    issues.push({ code: "visual-beat", message: "Visual Beat timing 必须连续、递增且位于 Task 计划时长内。" });
  }

  const incomingContext = snapshot.generationContextLinks.filter((link) => link.targetTaskId === taskId);
  if (incomingContext.some((link) => link.stale)) {
    issues.push({ code: "context", message: "Generation Context 已过期，需要更新或明确保留现有结果。" });
  }
  if (incomingContext.some((link) => link.kind !== "semantic" && !link.sourceResultId)) {
    issues.push({ code: "context", message: "Generation Context 缺少可用的上游 Result。" });
  }
  if (!providerOnline) issues.push({ code: "provider", message: "Video Generation Provider 当前离线。" });
  return issues;
}

export function markTaskReady(
  snapshot: StoryboardDomainSnapshot,
  taskId: string,
  profile: GenerationProfileInput,
  providerOnline: boolean,
) {
  const issues = validateTaskReadiness(snapshot, taskId, profile, providerOnline);
  if (issues.length > 0) return { snapshot, issues, ready: false };
  return {
    snapshot: {
      ...snapshot,
      tasks: snapshot.tasks.map((task) => task.id === taskId ? { ...task, state: "ready" as const } : task),
    },
    issues,
    ready: true,
  };
}

export function queueReadyTasks(
  snapshot: StoryboardDomainSnapshot,
  taskIds: string[],
  profiles: readonly GenerationProfileInput[],
  createdAt = "2026-09-12T00:00:00.000Z",
) {
  const requested = new Set(taskIds);
  const queuedTasks = snapshot.tasks.filter((task) => requested.has(task.id) && task.state === "ready");
  const queuedIds = queuedTasks.map((task) => task.id);
  const queued = new Set(queuedIds);
  const skippedIds = snapshot.tasks.filter((task) => requested.has(task.id) && !queued.has(task.id)).map((task) => task.id);
  const jobs: Job[] = queuedTasks.map((task, index) => {
    const profile = profiles.find((item) => item.id === task.generationProfileId);
    if (!profile) throw new Error(`Unknown Generation Profile: ${task.generationProfileId}`);
    return {
      id: `job-${task.id}-${snapshot.jobs.length + index + 1}`,
      taskId: task.id,
      providerId: "fake-video-provider",
      state: "queued",
      progress: 0,
      taskContentSnapshot: {
        title: task.title,
        summary: task.summary,
        scriptSource: task.scriptSource,
        userIntent: task.userIntent,
        visualBeats: task.visualBeats.map((beat) => ({ ...beat })),
        plannedDurationSeconds: task.plannedDurationSeconds,
      },
      finalPromptSnapshot: task.finalPrompt,
      assetsSnapshot: resolveTaskAssetSnapshots(snapshot, task.id),
      generationProfileSnapshot: { id: profile.id, capability: { ...profile.capability } },
      paramsSnapshot: { ...task.generationParams },
      contextSnapshot: snapshot.generationContextLinks
        .filter((link) => link.targetTaskId === task.id)
        .map((link) => ({ ...link })),
      createdAt,
    };
  });
  const jobIdByTaskId = new Map(jobs.map((job) => [job.taskId, job.id]));

  return {
    snapshot: {
      ...snapshot,
      tasks: snapshot.tasks.map((task) => queued.has(task.id) ? {
        ...task,
        state: "queued" as const,
        jobIds: [...task.jobIds, jobIdByTaskId.get(task.id)!],
      } : task),
      jobs: [...snapshot.jobs, ...jobs],
    },
    queuedIds,
    skippedIds,
    jobIds: jobs.map((job) => job.id),
  };
}

export function refreshTaskContext(snapshot: StoryboardDomainSnapshot, taskId: string) {
  const refreshedLinkIds: string[] = [];
  const generationContextLinks = snapshot.generationContextLinks.map((link) => {
    if (link.targetTaskId !== taskId) return link;
    const sourceTask = snapshot.tasks.find((task) => task.id === link.sourceTaskId);
    const sourceResultId = sourceTask?.primaryResultId;
    const stale = link.kind !== "semantic" && !sourceResultId;
    if (!stale) refreshedLinkIds.push(link.id);
    return { ...link, sourceResultId, stale };
  });

  return {
    snapshot: {
      ...snapshot,
      generationContextLinks,
      tasks: snapshot.tasks.map((task) => task.id === taskId && task.state === "context-stale"
        ? { ...task, state: generationContextLinks.some((link) => link.targetTaskId === taskId && link.stale) ? "context-stale" as const : "draft" as const }
        : task),
    },
    refreshedLinkIds,
  };
}

export function regenerateTaskAiPrompt(snapshot: StoryboardDomainSnapshot, taskId: string) {
  const task = snapshot.tasks.find((item) => item.id === taskId);
  if (!task) return snapshot;
  const revision = task.promptRevisions.length + 1;
  const output = `Mock AI Prompt Revision ${revision}: ${task.userIntent || task.summary}`;
  return {
    ...snapshot,
    tasks: snapshot.tasks.map((item) => item.id === taskId ? {
      ...item,
      aiPrompt: output,
      state: "prompt-ready" as const,
      promptRevisions: [...item.promptRevisions, {
        id: `prompt-revision-${taskId}-${revision}`,
        revision,
        providerId: "fake-prompt-provider",
        modelId: "mock-prompt-model",
        skillVersion: "task-prompt-v0.2",
        inputSnapshot: { taskId, userIntent: task.userIntent, visualBeats: task.visualBeats.map((beat) => ({ ...beat })) },
        output,
        createdAt: "2026-09-12T00:00:00.000Z",
      }],
    } : item),
  };
}

export function markTaskAndFollowingForRegeneration(snapshot: StoryboardDomainSnapshot, taskId: string) {
  const orderedTasks = snapshot.scenes
    .slice()
    .sort((left, right) => left.orderKey.localeCompare(right.orderKey))
    .flatMap((scene) => listTasksInStoryOrder(snapshot, scene.id));
  const start = orderedTasks.findIndex((task) => task.id === taskId);
  if (start < 0) return { snapshot, affectedTaskIds: [] };
  const affectedTaskIds = orderedTasks.slice(start).map((task) => task.id);
  const affected = new Set(affectedTaskIds);
  return {
    snapshot: {
      ...snapshot,
      tasks: snapshot.tasks.map((task) => affected.has(task.id) ? {
        ...task,
        state: task.id === taskId ? "draft" as const : "context-stale" as const,
      } : task),
      generationContextLinks: snapshot.generationContextLinks.map((link) => affected.has(link.targetTaskId)
        ? { ...link, stale: true }
        : link),
    },
    affectedTaskIds,
  };
}

export function setTaskPrimaryResult(
  snapshot: StoryboardDomainSnapshot,
  taskId: string,
  resultId: string,
) {
  const taskJobIds = new Set(snapshot.jobs.filter((job) => job.taskId === taskId).map((job) => job.id));
  const result = snapshot.results.find((item) => item.id === resultId && taskJobIds.has(item.jobId));
  if (!result) return { snapshot, changed: false, staleContextLinkIds: [] };
  const task = snapshot.tasks.find((item) => item.id === taskId);
  if (task?.primaryResultId === resultId) return { snapshot, changed: false, staleContextLinkIds: [] };

  const staleContextLinkIds = snapshot.generationContextLinks
    .filter((link) => link.sourceTaskId === taskId && link.sourceResultId !== resultId)
    .map((link) => link.id);
  const staleLinks = new Set(staleContextLinkIds);
  const staleTargets = new Set(snapshot.generationContextLinks
    .filter((link) => staleLinks.has(link.id))
    .map((link) => link.targetTaskId));

  return {
    snapshot: {
      ...snapshot,
      tasks: snapshot.tasks.map((item) => item.id === taskId
        ? { ...item, primaryResultId: resultId }
        : staleTargets.has(item.id) && !["queued", "running"].includes(item.state)
          ? { ...item, state: "context-stale" as const }
          : item),
      generationContextLinks: snapshot.generationContextLinks.map((link) => staleLinks.has(link.id)
        ? { ...link, stale: true }
        : link),
    },
    changed: true,
    staleContextLinkIds,
  };
}

export function setResultReviewState(
  snapshot: StoryboardDomainSnapshot,
  resultId: string,
  reviewState: "approved" | "rejected",
) {
  if (!snapshot.results.some((result) => result.id === resultId)) return snapshot;
  return {
    ...snapshot,
    results: snapshot.results.map((result) => result.id === resultId ? { ...result, reviewState } : result),
  };
}

export function approveAllPendingResults(snapshot: StoryboardDomainSnapshot) {
  const approvedResultIds = snapshot.results.filter((result) => result.reviewState === "pending").map((result) => result.id);
  const approved = new Set(approvedResultIds);
  return {
    snapshot: {
      ...snapshot,
      results: snapshot.results.map((result) => approved.has(result.id) ? { ...result, reviewState: "approved" as const } : result),
    },
    approvedResultIds,
  };
}

export function requestTaskRegeneration(snapshot: StoryboardDomainSnapshot, taskId: string) {
  if (!snapshot.tasks.some((task) => task.id === taskId)) return snapshot;
  return {
    ...snapshot,
    tasks: snapshot.tasks.map((task) => task.id === taskId ? { ...task, state: "ready" as const } : task),
  };
}
