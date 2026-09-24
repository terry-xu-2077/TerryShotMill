import type {
  GenerationTask,
  Scene,
  StoryboardDomainSnapshot,
  TaskAssetBinding,
} from "../../domain/storyboard";

function markTouchedContextStale(snapshot: StoryboardDomainSnapshot, taskIds: string[]) {
  const touched = new Set(taskIds);
  const staleTargetIds = new Set(
    snapshot.generationContextLinks
      .filter((link) => touched.has(link.sourceTaskId) || touched.has(link.targetTaskId))
      .map((link) => link.targetTaskId),
  );
  return {
    ...snapshot,
    generationContextLinks: snapshot.generationContextLinks.map((link) =>
      touched.has(link.sourceTaskId) || touched.has(link.targetTaskId) ? { ...link, stale: true } : link,
    ),
    tasks: snapshot.tasks.map((task) => staleTargetIds.has(task.id) && !["queued", "running"].includes(task.state)
      ? { ...task, state: "context-stale" as const }
      : task),
  };
}

function reindexScene(
  snapshot: StoryboardDomainSnapshot,
  sceneId: string,
  orderedTaskIds: string[],
): StoryboardDomainSnapshot["taskPlacements"] {
  const otherScenes = snapshot.taskPlacements.filter((placement) => placement.sceneId !== sceneId);
  return [
    ...otherScenes,
    ...orderedTaskIds.map((taskId, index) => ({
      taskId,
      sceneId,
      orderKey: String(index + 1).padStart(6, "0"),
    })),
  ];
}

export function insertTaskAfter(
  snapshot: StoryboardDomainSnapshot,
  task: GenerationTask,
  sceneId: string,
  afterTaskId?: string,
): StoryboardDomainSnapshot {
  const sceneTaskIds = snapshot.taskPlacements
    .filter((placement) => placement.sceneId === sceneId)
    .slice()
    .sort((left, right) => left.orderKey.localeCompare(right.orderKey))
    .map((placement) => placement.taskId);
  const anchorIndex = afterTaskId ? sceneTaskIds.indexOf(afterTaskId) : -1;
  const insertIndex = anchorIndex >= 0 ? anchorIndex + 1 : sceneTaskIds.length;
  const nextOrder = [...sceneTaskIds];
  nextOrder.splice(insertIndex, 0, task.id);

  return {
    ...snapshot,
    tasks: [...snapshot.tasks, task],
    taskPlacements: reindexScene(snapshot, sceneId, nextOrder),
  };
}

export function cloneTaskAsDraft(source: GenerationTask, id: string, number: string): GenerationTask {
  return {
    ...source,
    id,
    number,
    title: `${source.title} · 副本`,
    storyboardFrame: { ...source.storyboardFrame },
    visualBeats: source.visualBeats.map((beat, index) => ({ ...beat, id: `${id}-beat-${index + 1}` })),
    assetBindings: source.assetBindings.map((binding) => ({ ...binding })),
    promptRevisions: [],
    generationParams: { ...source.generationParams },
    contextLinkIds: [],
    state: "draft",
    progress: undefined,
    jobIds: [],
    primaryResultId: undefined,
  };
}

export function deleteTasksWithoutHistory(snapshot: StoryboardDomainSnapshot, requestedTaskIds: string[]) {
  const requested = new Set(requestedTaskIds);
  const protectedIds = snapshot.tasks
    .filter((task) => requested.has(task.id) && (task.jobIds.length > 0 || Boolean(task.primaryResultId)))
    .map((task) => task.id);
  const protectedSet = new Set(protectedIds);
  const deletedIds = snapshot.tasks
    .filter((task) => requested.has(task.id) && !protectedSet.has(task.id))
    .map((task) => task.id);
  const deletedSet = new Set(deletedIds);
  const generationContextLinks = snapshot.generationContextLinks.filter(
    (link) => !deletedSet.has(link.sourceTaskId) && !deletedSet.has(link.targetTaskId),
  );
  const survivingLinkIds = new Set(generationContextLinks.map((link) => link.id));

  return {
    snapshot: {
      ...snapshot,
      tasks: snapshot.tasks
        .filter((task) => !deletedSet.has(task.id))
        .map((task) => ({ ...task, contextLinkIds: task.contextLinkIds.filter((id) => survivingLinkIds.has(id)) })),
      taskPlacements: snapshot.taskPlacements.filter((placement) => !deletedSet.has(placement.taskId)),
      generationContextLinks,
    },
    deletedIds,
    protectedIds,
  };
}

export function moveTasksInStoryOrder(
  snapshot: StoryboardDomainSnapshot,
  requestedTaskIds: string[],
  targetSceneId: string,
  beforeTaskId?: string,
) {
  const requested = new Set(requestedTaskIds);
  const currentOrders = new Map(snapshot.scenes.map((scene) => [
    scene.id,
    snapshot.taskPlacements
      .filter((placement) => placement.sceneId === scene.id)
      .slice()
      .sort((left, right) => left.orderKey.localeCompare(right.orderKey))
      .map((placement) => placement.taskId),
  ]));
  const movedTaskIds = snapshot.taskPlacements
    .slice()
    .sort((left, right) => {
      const leftScene = snapshot.scenes.find((scene) => scene.id === left.sceneId)?.orderKey ?? "";
      const rightScene = snapshot.scenes.find((scene) => scene.id === right.sceneId)?.orderKey ?? "";
      return leftScene.localeCompare(rightScene) || left.orderKey.localeCompare(right.orderKey);
    })
    .filter((placement) => requested.has(placement.taskId))
    .map((placement) => placement.taskId);

  if (movedTaskIds.length === 0 || !snapshot.scenes.some((scene) => scene.id === targetSceneId)) {
    return { snapshot, movedTaskIds: [], staleContextLinkIds: [], changed: false };
  }

  const movedSet = new Set(movedTaskIds);
  const nextOrders = new Map<string, string[]>();
  for (const scene of snapshot.scenes) {
    nextOrders.set(
      scene.id,
      snapshot.taskPlacements
        .filter((placement) => placement.sceneId === scene.id && !movedSet.has(placement.taskId))
        .slice()
        .sort((left, right) => left.orderKey.localeCompare(right.orderKey))
        .map((placement) => placement.taskId),
    );
  }

  const targetOrder = nextOrders.get(targetSceneId) ?? [];
  const requestedInsertIndex = beforeTaskId ? targetOrder.indexOf(beforeTaskId) : -1;
  const insertIndex = requestedInsertIndex >= 0 ? requestedInsertIndex : targetOrder.length;
  targetOrder.splice(insertIndex, 0, ...movedTaskIds);

  const nextPlacements = snapshot.scenes.flatMap((scene) =>
    (nextOrders.get(scene.id) ?? []).map((taskId, index) => ({
      taskId,
      sceneId: scene.id,
      orderKey: String(index + 1).padStart(6, "0"),
    })),
  );
  const changed = snapshot.scenes.some((scene) =>
    JSON.stringify(currentOrders.get(scene.id) ?? []) !== JSON.stringify(nextOrders.get(scene.id) ?? []),
  );

  if (!changed) return { snapshot, movedTaskIds, staleContextLinkIds: [], changed: false };

  const staleContextLinkIds = snapshot.generationContextLinks
    .filter((link) => movedSet.has(link.sourceTaskId) || movedSet.has(link.targetTaskId))
    .map((link) => link.id);
  const staleSet = new Set(staleContextLinkIds);

  return {
    snapshot: {
      ...snapshot,
      taskPlacements: nextPlacements,
      generationContextLinks: snapshot.generationContextLinks.map((link) =>
        staleSet.has(link.id) ? { ...link, stale: true } : link,
      ),
    },
    movedTaskIds,
    staleContextLinkIds,
    changed: true,
  };
}

export function updateTaskIntent(
  snapshot: StoryboardDomainSnapshot,
  taskId: string,
  patch: Partial<Pick<GenerationTask,
    "title" | "summary" | "scriptSource" | "userIntent" | "plannedDurationSeconds" | "generationProfileId" | "generationProfileLabel"
  >>,
) {
  const updated = {
    ...snapshot,
    tasks: snapshot.tasks.map((task) => task.id === taskId ? { ...task, ...patch } : task),
  };
  return markTouchedContextStale(updated, [taskId]);
}

export function updateTaskComposerFields(
  snapshot: StoryboardDomainSnapshot,
  taskId: string,
  patch: Partial<Pick<GenerationTask,
    "scriptSource" | "userIntent" | "aiPrompt" | "finalPrompt" | "visualBeats" | "generationProfileId" | "generationProfileLabel" | "generationParams"
  >>,
) {
  const updated = {
    ...snapshot,
    tasks: snapshot.tasks.map((task) => task.id === taskId ? {
      ...task,
      ...patch,
      visualBeats: patch.visualBeats?.map((beat) => ({ ...beat })) ?? task.visualBeats,
      generationParams: patch.generationParams ? { ...patch.generationParams } : task.generationParams,
    } : task),
  };
  return markTouchedContextStale(updated, [taskId]);
}

export function updateSceneMetadata(
  snapshot: StoryboardDomainSnapshot,
  sceneId: string,
  patch: Partial<Pick<Scene, "title" | "summary" | "location" | "timeOfDay" | "notes">>,
) {
  return {
    ...snapshot,
    scenes: snapshot.scenes.map((scene) => scene.id === sceneId ? { ...scene, ...patch } : scene),
  };
}

export function applyProfileToTasks(
  snapshot: StoryboardDomainSnapshot,
  taskIds: string[],
  profile: { id: string; label: string },
) {
  const requested = new Set(taskIds);
  const updated = {
    ...snapshot,
    tasks: snapshot.tasks.map((task) => requested.has(task.id)
      ? { ...task, generationProfileId: profile.id, generationProfileLabel: profile.label }
      : task),
  };
  return markTouchedContextStale(updated, taskIds);
}

export function addAssetBindingToTasks(
  snapshot: StoryboardDomainSnapshot,
  taskIds: string[],
  binding: TaskAssetBinding,
) {
  const requested = new Set(taskIds);
  const updated = {
    ...snapshot,
    tasks: snapshot.tasks.map((task) => {
      if (!requested.has(task.id) || task.assetBindings.some((item) => item.assetId === binding.assetId)) return task;
      return { ...task, assetBindings: [...task.assetBindings, { ...binding }] };
    }),
  };
  return markTouchedContextStale(updated, taskIds);
}

export function replaceTaskAssetBindings(
  snapshot: StoryboardDomainSnapshot,
  taskId: string,
  assetBindings: TaskAssetBinding[],
) {
  const updated = {
    ...snapshot,
    tasks: snapshot.tasks.map((task) => task.id === taskId
      ? { ...task, assetBindings: assetBindings.map((binding) => ({ ...binding })) }
      : task),
  };
  return markTouchedContextStale(updated, [taskId]);
}
