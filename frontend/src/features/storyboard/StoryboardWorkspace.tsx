import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import {
  ChevronLeft,
  Clock3,
  Copy,
  Film,
  LayoutPanelLeft,
  ListPlus,
  MapPin,
  PanelRightClose,
  PanelRightOpen,
  Play,
  Plus,
  Sparkles,
  Trash2,
} from "lucide-react";
import { Button } from "terry-react-ui-library";

import {
  getTaskPlacement,
  listContextForTask,
  listResultsForTask,
  listTasksInStoryOrder,
  type GenerationTask,
  type StoryboardDomainSnapshot,
  type TaskProposal,
} from "../../domain/storyboard";
import { storyboardForDensity, type StoryboardDensity } from "../../mock/storyboardScenarios";
import { getMockGenerationProfile, mockGenerationProfiles } from "../../mock/generationProfiles";
import { Dialog, PortalSelect } from "../../ui/overlay";
import {
  addAssetBindingToTasks,
  applyProfileToTasks,
  cloneTaskAsDraft,
  deleteTasksWithoutHistory,
  insertTaskAfter,
  moveTasksInStoryOrder,
  replaceTaskAssetBindings,
  updateTaskComposerFields,
  updateSceneMetadata,
  updateTaskIntent,
} from "./storyboardMutations";
import {
  markTaskAndFollowingForRegeneration,
  markTaskReady,
  queueReadyTasks,
  refreshTaskContext,
  regenerateTaskAiPrompt,
  validateTaskReadiness,
} from "./storyboardExecution";
import { StoryboardTaskCard } from "./StoryboardTaskCard";
import { ScriptToTasksDialog } from "./ScriptToTasksDialog";
import { AssetPickerDialog } from "../assets/AssetPickerDialog";
import { TaskComposer } from "../../components/TaskComposer";
import type { GenerationTaskCardView } from "../../types";
import { StoryReel } from "./StoryReel";

type StoryboardWorkspaceProps = {
  density: StoryboardDensity;
  providerOnline?: boolean;
  value?: StoryboardDomainSnapshot;
  onChange?: Dispatch<SetStateAction<StoryboardDomainSnapshot>>;
  focusTaskId?: string | null;
  onOpenTask?: (task: GenerationTask) => void;
};

export function StoryboardWorkspace({
  density,
  providerOnline = true,
  value,
  onChange,
  focusTaskId,
  onOpenTask,
}: StoryboardWorkspaceProps) {
  const initialSnapshot = useMemo(() => storyboardForDensity(density), [density]);
  const [localSnapshot, setLocalSnapshot] = useState(initialSnapshot);
  const isControlled = value !== undefined;
  const snapshot = value ?? localSnapshot;
  const setSnapshot = onChange ?? setLocalSnapshot;
  const scenes = useMemo(
    () => snapshot.scenes.slice().sort((left, right) => left.orderKey.localeCompare(right.orderKey)),
    [snapshot],
  );
  const [selectedSceneId, setSelectedSceneId] = useState(scenes[0]?.id ?? "");
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([]);
  const [selectionAnchorId, setSelectionAnchorId] = useState<string | null>(null);
  const [sceneNavigatorCollapsed, setSceneNavigatorCollapsed] = useState(false);
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [operationMessage, setOperationMessage] = useState("");
  const [clipboardTaskIds, setClipboardTaskIds] = useState<string[]>([]);
  const [draggedTaskIds, setDraggedTaskIds] = useState<string[]>([]);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [batchSceneId, setBatchSceneId] = useState(scenes[0]?.id ?? "");
  const [batchProfileId, setBatchProfileId] = useState(mockGenerationProfiles[0].id);
  const [scriptDialogOpen, setScriptDialogOpen] = useState(false);
  const [assetPickerOpen, setAssetPickerOpen] = useState(false);
  const [composerTaskId, setComposerTaskId] = useState<string | null>(null);
  const [reelOpen, setReelOpen] = useState(false);
  const localSequence = useRef(0);

  useEffect(() => {
    if (!isControlled) setLocalSnapshot(initialSnapshot);
    setSelectedTaskIds([]);
    setSelectionAnchorId(null);
    setDeleteDialogOpen(false);
    setOperationMessage("");
    setClipboardTaskIds([]);
    setDraggedTaskIds([]);
    setDropTarget(null);
    setBatchSceneId(initialSnapshot.scenes[0]?.id ?? "");
    setBatchProfileId(mockGenerationProfiles[0].id);
    setScriptDialogOpen(false);
    setAssetPickerOpen(false);
    setComposerTaskId(null);
    setReelOpen(false);
  }, [initialSnapshot, isControlled]);

  useEffect(() => {
    if (!focusTaskId || !snapshot.tasks.some((task) => task.id === focusTaskId)) return;
    const placement = getTaskPlacement(snapshot, focusTaskId);
    if (placement) setSelectedSceneId(placement.sceneId);
    setSelectedTaskIds([focusTaskId]);
    setSelectionAnchorId(focusTaskId);
  }, [focusTaskId, snapshot]);

  useEffect(() => {
    if (!scenes.some((scene) => scene.id === selectedSceneId)) setSelectedSceneId(scenes[0]?.id ?? "");
    const availableTaskIds = new Set(snapshot.tasks.map((task) => task.id));
    setSelectedTaskIds((current) => current.filter((id) => availableTaskIds.has(id)));
  }, [scenes, selectedSceneId, snapshot.tasks]);

  const selectedScene = scenes.find((scene) => scene.id === selectedSceneId) ?? scenes[0];
  const orderedTasks = useMemo(
    () => scenes.flatMap((scene) => listTasksInStoryOrder(snapshot, scene.id)),
    [scenes, snapshot],
  );
  const selectedTasks = orderedTasks.filter((task) => selectedTaskIds.includes(task.id));
  const selectedTask = selectedTasks.length === 1 ? selectedTasks[0] : undefined;
  const composerTask = composerTaskId ? snapshot.tasks.find((task) => task.id === composerTaskId) : undefined;
  const totalDuration = snapshot.tasks.reduce((total, task) => total + task.plannedDurationSeconds, 0);

  const sceneSummary = (sceneId: string) => {
    const tasks = listTasksInStoryOrder(snapshot, sceneId);
    return {
      tasks,
      duration: tasks.reduce((total, task) => total + task.plannedDurationSeconds, 0),
      running: tasks.filter((task) => task.state === "running").length,
      needsAttention: tasks.filter((task) => ["failed", "blocked", "context-stale"].includes(task.state)).length,
    };
  };

  const selectedSceneSummary = selectedScene ? sceneSummary(selectedScene.id) : undefined;
  const selectedTaskContexts = selectedTask ? listContextForTask(snapshot, selectedTask.id) : [];
  const selectedTaskResults = selectedTask ? listResultsForTask(snapshot, selectedTask.id) : [];
  const selectedTaskIndex = selectedTask ? orderedTasks.findIndex((task) => task.id === selectedTask.id) : -1;
  const previousTask = selectedTaskIndex > 0 ? orderedTasks[selectedTaskIndex - 1] : undefined;
  const nextTask = selectedTaskIndex >= 0 ? orderedTasks[selectedTaskIndex + 1] : undefined;
  const selectedProfile = selectedTask ? getMockGenerationProfile(selectedTask.generationProfileId) : undefined;
  const selectedProfileWarnings = selectedTask && selectedProfile ? [
    selectedTask.visualBeats.length > 1 && !selectedProfile.capability.multiShotPrompt
      ? "当前 Profile 不支持多镜头提示词。"
      : "",
    selectedProfile.capability.maxDurationSeconds && selectedTask.plannedDurationSeconds > selectedProfile.capability.maxDurationSeconds
      ? `计划时长超过 Profile 上限 ${selectedProfile.capability.maxDurationSeconds}s。`
      : "",
  ].filter(Boolean) : [];
  const selectedReadyIssues = selectedTask && selectedProfile
    ? validateTaskReadiness(snapshot, selectedTask.id, selectedProfile, providerOnline)
    : [];

  const nextLocalIdentity = () => {
    localSequence.current += 1;
    const sequence = String(localSequence.current).padStart(3, "0");
    return { id: `task-local-${sequence}`, number: `LOCAL-${sequence}` };
  };

  const selectTask = (task: GenerationTask, event: React.MouseEvent) => {
    const placement = getTaskPlacement(snapshot, task.id);
    if (placement) setSelectedSceneId(placement.sceneId);
    setOperationMessage("");

    if (event.shiftKey && selectionAnchorId) {
      const anchorIndex = orderedTasks.findIndex((item) => item.id === selectionAnchorId);
      const targetIndex = orderedTasks.findIndex((item) => item.id === task.id);
      if (anchorIndex >= 0 && targetIndex >= 0) {
        const [start, end] = [anchorIndex, targetIndex].sort((left, right) => left - right);
        const range = orderedTasks.slice(start, end + 1).map((item) => item.id);
        setSelectedTaskIds(event.ctrlKey || event.metaKey
          ? (current) => [...new Set([...current, ...range])]
          : range);
        return;
      }
    }

    if (event.ctrlKey || event.metaKey) {
      setSelectedTaskIds((current) => current.includes(task.id)
        ? current.filter((id) => id !== task.id)
        : [...current, task.id]);
      setSelectionAnchorId(task.id);
      return;
    }

    setSelectedTaskIds([task.id]);
    setSelectionAnchorId(task.id);
  };

  const createTask = (inheritProfile: boolean, requestedSceneId?: string) => {
    const source = selectedTasks.at(-1);
    const sourcePlacement = source ? getTaskPlacement(snapshot, source.id) : undefined;
    const sceneId = requestedSceneId ?? sourcePlacement?.sceneId ?? selectedScene?.id ?? scenes[0]?.id;
    if (!sceneId) return;

    const identity = nextLocalIdentity();
    const task: GenerationTask = {
      ...identity,
      title: "未命名生成任务",
      summary: inheritProfile && source ? `已继承 ${source.generationProfileLabel}，等待补充新的生成意图。` : "等待补充剧本与创作意图。",
      scriptSource: "",
      userIntent: "",
      storyboardFrame: { sourceType: "placeholder", updatedAt: "2026-09-12T00:00:00.000Z" },
      visualBeats: [],
      assetBindings: [],
      plannedDurationSeconds: 0,
      generationProfileId: inheritProfile && source ? source.generationProfileId : "profile-h3-multi-shot",
      generationProfileLabel: inheritProfile && source ? source.generationProfileLabel : "H3 · Multi-shot",
      aiPrompt: "",
      finalPrompt: "",
      promptRevisions: [],
      generationParams: inheritProfile && source ? { ...source.generationParams } : { aspectRatio: "16:9" },
      contextLinkIds: [],
      state: "draft",
      jobIds: [],
    };
    const anchorId = sourcePlacement?.sceneId === sceneId ? source?.id : undefined;

    setSnapshot((current) => insertTaskAfter(current, task, sceneId, anchorId));
    setSelectedSceneId(sceneId);
    setSelectedTaskIds([task.id]);
    setSelectionAnchorId(task.id);
    setOperationMessage(inheritProfile && source ? "已新建下一个 Task，并继承 Generation Profile" : "已创建空白 Task");
  };

  const duplicateTasks = (sourceTasks: GenerationTask[]) => {
    if (sourceTasks.length === 0) return;
    let nextSnapshot = snapshot;
    const copiedIds: string[] = [];

    sourceTasks.forEach((source) => {
      const placement = getTaskPlacement(snapshot, source.id);
      if (!placement) return;
      const identity = nextLocalIdentity();
      const copy = cloneTaskAsDraft(source, identity.id, identity.number);
      nextSnapshot = insertTaskAfter(nextSnapshot, copy, placement.sceneId, source.id);
      copiedIds.push(copy.id);
    });

    setSnapshot(nextSnapshot);
    setSelectedTaskIds(copiedIds);
    setSelectionAnchorId(copiedIds.at(-1) ?? null);
    setOperationMessage(`已复制 ${copiedIds.length} 个 Task；未复制 Job、Result 与 Context`);
  };

  const duplicateSelectedTasks = () => duplicateTasks(selectedTasks);

  const moveTasks = (taskIds: string[], targetSceneId: string, beforeTaskId?: string) => {
    const result = moveTasksInStoryOrder(snapshot, taskIds, targetSceneId, beforeTaskId);
    setDraggedTaskIds([]);
    setDropTarget(null);
    if (!result.changed) {
      setOperationMessage("Story Order 未发生变化");
      return;
    }

    setSnapshot(result.snapshot);
    setSelectedSceneId(targetSceneId);
    setSelectedTaskIds(result.movedTaskIds);
    setSelectionAnchorId(result.movedTaskIds.at(-1) ?? null);
    setOperationMessage(
      result.staleContextLinkIds.length > 0
        ? `已移动 ${result.movedTaskIds.length} 个 Task；${result.staleContextLinkIds.length} 条 Context Link 标记为待复核`
        : `已移动 ${result.movedTaskIds.length} 个 Task；Job、Result 与 Context Link 保持不变`,
    );
  };

  const startTaskDrag = (task: GenerationTask, event: React.DragEvent) => {
    const taskIds = selectedTaskIds.includes(task.id) ? selectedTaskIds : [task.id];
    if (!selectedTaskIds.includes(task.id)) {
      setSelectedTaskIds([task.id]);
      setSelectionAnchorId(task.id);
    }
    setDraggedTaskIds(taskIds);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", taskIds.join(","));
  };

  const handleWorkspaceKeyDown = (event: React.KeyboardEvent) => {
    const target = event.target as HTMLElement;
    if (["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(target.tagName)) return;
    const command = event.ctrlKey || event.metaKey;

    if (command && event.key.toLowerCase() === "d" && selectedTasks.length > 0) {
      event.preventDefault();
      duplicateSelectedTasks();
      return;
    }
    if (command && event.key.toLowerCase() === "c" && selectedTasks.length > 0) {
      event.preventDefault();
      setClipboardTaskIds(selectedTasks.map((task) => task.id));
      setOperationMessage(`已复制 ${selectedTasks.length} 个 Task 到 Storyboard 剪贴板`);
      return;
    }
    if (command && event.key.toLowerCase() === "v" && clipboardTaskIds.length > 0) {
      event.preventDefault();
      duplicateTasks(orderedTasks.filter((task) => clipboardTaskIds.includes(task.id)));
      return;
    }
    if (event.key === "Delete" && selectedTasks.length > 0) {
      event.preventDefault();
      setDeleteDialogOpen(true);
      return;
    }
    if (event.key === "Escape") {
      setSelectedTaskIds([]);
      setSelectionAnchorId(null);
      setOperationMessage("");
      return;
    }
    if (["ArrowLeft", "ArrowUp", "ArrowRight", "ArrowDown"].includes(event.key) && orderedTasks.length > 0) {
      event.preventDefault();
      const currentId = selectedTaskIds.at(-1);
      const currentIndex = Math.max(0, orderedTasks.findIndex((task) => task.id === currentId));
      const delta = ["ArrowLeft", "ArrowUp"].includes(event.key) ? -1 : 1;
      const nextIndex = Math.min(orderedTasks.length - 1, Math.max(0, currentIndex + delta));
      const nextTask = orderedTasks[nextIndex];
      setSelectedTaskIds(event.shiftKey
        ? [...new Set([...selectedTaskIds, nextTask.id])]
        : [nextTask.id]);
      setSelectionAnchorId(nextTask.id);
      const placement = getTaskPlacement(snapshot, nextTask.id);
      if (placement) setSelectedSceneId(placement.sceneId);
      requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-task-id="${nextTask.id}"]`)?.focus());
    }
  };

  const confirmDelete = () => {
    const result = deleteTasksWithoutHistory(snapshot, selectedTaskIds);
    setSnapshot(result.snapshot);
    setSelectedTaskIds(result.protectedIds);
    setSelectionAnchorId(result.protectedIds.at(-1) ?? null);
    setDeleteDialogOpen(false);

    if (result.deletedIds.length > 0 && result.protectedIds.length > 0) {
      setOperationMessage(`已删除 ${result.deletedIds.length} 个 Task；${result.protectedIds.length} 个含历史记录的 Task 已保留`);
    } else if (result.deletedIds.length > 0) {
      setOperationMessage(`已删除 ${result.deletedIds.length} 个 Task`);
    } else {
      setOperationMessage("所选 Task 含 Job 或 Result 历史，不能直接删除");
    }
  };

  const protectedDeleteCount = selectedTasks.filter((task) => task.jobIds.length > 0 || Boolean(task.primaryResultId)).length;
  const deletableTaskCount = selectedTasks.length - protectedDeleteCount;

  const applyBatchProfile = () => {
    const profile = getMockGenerationProfile(batchProfileId);
    setSnapshot((current) => applyProfileToTasks(current, selectedTaskIds, profile));
    setOperationMessage(`已将 ${selectedTaskIds.length} 个 Task 设置为 ${profile.label}`);
  };

  const bindBatchAsset = () => {
    setSnapshot((current) => addAssetBindingToTasks(current, selectedTaskIds, {
      assetId: "asset-rain-audio",
      role: "audio",
      notes: "由 Batch Inspector 绑定",
    }));
    setOperationMessage(`已向 ${selectedTaskIds.length} 个 Task 绑定雨声参考资产`);
  };

  const queueBatch = () => {
    if (!providerOnline) {
      setOperationMessage("Provider 当前离线，所选 Task 均未加入队列");
      return;
    }
    const result = queueReadyTasks(snapshot, selectedTaskIds, mockGenerationProfiles);
    setSnapshot(result.snapshot);
    setOperationMessage(`已加入队列 ${result.queuedIds.length} 个；跳过 ${result.skippedIds.length} 个未 Ready Task`);
  };

  const runSelectedReadyValidation = () => {
    if (!selectedTask || !selectedProfile) return;
    const result = markTaskReady(snapshot, selectedTask.id, selectedProfile, providerOnline);
    setSnapshot(result.snapshot);
    setOperationMessage(result.ready
      ? `${selectedTask.number} 已通过 Ready Validation`
      : `Ready Validation 未通过：${result.issues.length} 项需要处理`);
  };

  const queueSelectedTask = () => {
    if (!selectedTask) return;
    const result = queueReadyTasks(snapshot, [selectedTask.id], mockGenerationProfiles);
    setSnapshot(result.snapshot);
    setOperationMessage(result.jobIds.length > 0
      ? `${selectedTask.number} 已加入队列，并创建不可变 Job 快照 ${result.jobIds[0]}`
      : `${selectedTask.number} 尚未 Ready，未加入队列`);
  };

  const refreshSelectedContext = () => {
    if (!selectedTask) return;
    const result = refreshTaskContext(snapshot, selectedTask.id);
    setSnapshot(result.snapshot);
    setOperationMessage(result.refreshedLinkIds.length > 0
      ? `已从上游 Primary Result 更新 ${result.refreshedLinkIds.length} 条 Context Link`
      : "没有可更新的 Generation Context");
  };

  const regenerateSelectedPrompt = () => {
    if (!selectedTask) return;
    setSnapshot(regenerateTaskAiPrompt(snapshot, selectedTask.id));
    setOperationMessage("已生成新的 AI Prompt Revision；Final Prompt 保持不变");
  };

  const regenerateFromSelectedTask = () => {
    if (!selectedTask) return;
    const result = markTaskAndFollowingForRegeneration(snapshot, selectedTask.id);
    setSnapshot(result.snapshot);
    setOperationMessage(`已将当前及后续 ${result.affectedTaskIds.length} 个 Task 标记为重新生成；历史 Result 保持不变`);
  };

  const acceptTaskProposals = (proposals: TaskProposal[]) => {
    let nextSnapshot = snapshot;
    const createdIds: string[] = [];
    for (const proposal of proposals) {
      const identity = nextLocalIdentity();
      const task: GenerationTask = {
        ...identity,
        title: proposal.title,
        summary: proposal.summary,
        scriptSource: proposal.scriptExcerpt,
        userIntent: proposal.userIntent,
        storyboardFrame: { sourceType: "placeholder", updatedAt: "2026-09-12T00:00:00.000Z" },
        visualBeats: proposal.visualBeats.map((beat, index) => ({ ...beat, id: `${identity.id}-beat-${index + 1}` })),
        assetBindings: proposal.suggestedAssetIds.map((assetId) => ({ assetId, role: "reference" as const })),
        plannedDurationSeconds: proposal.plannedDurationSeconds,
        generationProfileId: proposal.suggestedProfileId,
        generationProfileLabel: proposal.suggestedProfileLabel,
        aiPrompt: "",
        finalPrompt: "",
        promptRevisions: [],
        generationParams: { aspectRatio: "16:9" },
        contextLinkIds: [],
        state: "draft",
        jobIds: [],
      };
      nextSnapshot = insertTaskAfter(nextSnapshot, task, proposal.targetSceneId);
      createdIds.push(task.id);
    }
    setSnapshot(nextSnapshot);
    setSelectedTaskIds(createdIds);
    setSelectionAnchorId(createdIds.at(-1) ?? null);
    if (proposals.at(-1)?.targetSceneId) setSelectedSceneId(proposals.at(-1)!.targetSceneId);
    setOperationMessage(`已从确认的 Proposal 创建 ${createdIds.length} 个正式 Task`);
  };

  const openTaskComposer = (task: GenerationTask) => {
    setComposerTaskId(task.id);
    onOpenTask?.(task);
  };

  if (composerTask) {
    const composerView: GenerationTaskCardView = {
      id: composerTask.id,
      number: composerTask.number,
      title: composerTask.title,
      summary: composerTask.summary,
      state: composerTask.state,
      assetCount: composerTask.assetBindings.length,
      plannedDurationLabel: composerTask.plannedDurationSeconds ? `${composerTask.plannedDurationSeconds}s` : "—",
      visualBeatCount: composerTask.visualBeats.length,
      progress: composerTask.progress,
      assetBindings: composerTask.assetBindings.map((binding) => ({ ...binding })),
      scriptSource: composerTask.scriptSource,
      userIntent: composerTask.userIntent,
      aiPrompt: composerTask.aiPrompt,
      finalPrompt: composerTask.finalPrompt,
      visualBeats: composerTask.visualBeats.map((beat) => ({ ...beat })),
      generationProfileId: composerTask.generationProfileId,
      generationProfileLabel: composerTask.generationProfileLabel,
    };
    return (
      <TaskComposer
        key={composerTask.id}
        task={composerView}
        onClose={() => setComposerTaskId(null)}
        onTaskChange={(patch) => setSnapshot((current) => updateTaskComposerFields(current, composerTask.id, patch))}
      />
    );
  }

  if (reelOpen) return <StoryReel snapshot={snapshot} onClose={() => setReelOpen(false)} />;

  return (
    <>
    <div
      className={`storyboard-shell ${sceneNavigatorCollapsed ? "is-scene-nav-collapsed" : ""} ${inspectorCollapsed ? "is-inspector-collapsed" : ""}`}
      data-testid="storyboard-workspace"
      onKeyDown={handleWorkspaceKeyDown}
    >
      {sceneNavigatorCollapsed ? (
        <div className="storyboard-collapsed-rail is-left">
          <button type="button" onClick={() => setSceneNavigatorCollapsed(false)} aria-label="展开 Scene Navigator">
            <LayoutPanelLeft size={17} />
          </button>
        </div>
      ) : (
        <aside className="storyboard-scene-nav" aria-label="Scene Navigator">
          <header>
            <div><span className="eyebrow">STORY ORDER</span><h2>Scenes</h2></div>
            <button type="button" onClick={() => setSceneNavigatorCollapsed(true)} aria-label="折叠 Scene Navigator">
              <ChevronLeft size={16} />
            </button>
          </header>
          <div className="storyboard-scene-list">
            {scenes.map((scene) => {
              const summary = sceneSummary(scene.id);
              return (
                <button
                  key={scene.id}
                  type="button"
                  className={scene.id === selectedScene?.id && selectedTaskIds.length === 0 ? "is-selected" : ""}
                  onClick={() => {
                    setSelectedSceneId(scene.id);
                    setSelectedTaskIds([]);
                    setSelectionAnchorId(null);
                  }}
                >
                  <span>{scene.number}</span>
                  <strong>{scene.title || "未命名场景"}</strong>
                  <small>{scene.location || "地点待定"} · {scene.timeOfDay || "时间待定"}</small>
                  <em>{summary.tasks.length} Tasks · {summary.duration}s</em>
                </button>
              );
            })}
          </div>
          <Button><Plus size={14} /> 新建 Scene</Button>
        </aside>
      )}

      <section className="storyboard-canvas" aria-label="Storyboard Task Board">
        <header className="storyboard-workspace-head">
          <div>
            <span className="eyebrow">STORYBOARD-STYLE TASK WORKSPACE</span>
            <h1>分镜式任务工作台</h1>
            <p>每张卡片都是生成任务，可在一个 Task 内描述多个镜头。</p>
          </div>
          <div className="storyboard-total">
            <span><Film size={14} /> {snapshot.tasks.length} Tasks</span>
            <span><Clock3 size={14} /> {totalDuration}s planned</span>
            <Button onClick={() => setReelOpen(true)}><Play size={14} /> Story Reel</Button>
            <Button variant="accent" onClick={() => setScriptDialogOpen(true)}><Sparkles size={15} /> 从剧本创建任务</Button>
          </div>
        </header>

        <div className="storyboard-task-toolbar" aria-label="Task 操作">
          <Button variant="accent" onClick={() => createTask(false)}><Plus size={14} /> 新建 Task</Button>
          <Button onClick={() => createTask(true)}><ListPlus size={14} /> 新建下一个</Button>
          <Button onClick={duplicateSelectedTasks} disabled={selectedTaskIds.length === 0}><Copy size={14} /> 复制</Button>
          <Button className="storyboard-danger-button" onClick={() => setDeleteDialogOpen(true)} disabled={selectedTaskIds.length === 0}>
            <Trash2 size={14} /> 删除
          </Button>
          {operationMessage && <span className="storyboard-operation-message" role="status">{operationMessage}</span>}
        </div>

        {selectedTaskIds.length > 1 && (
          <section className="storyboard-batch-bar" aria-label="Storyboard 批量操作">
            <strong>已选择 {selectedTaskIds.length} 个 Task</strong>
            <span />
            <Button onClick={duplicateSelectedTasks}><Copy size={13} /> 复制</Button>
            <Button className="storyboard-danger-button" onClick={() => setDeleteDialogOpen(true)}><Trash2 size={13} /> 删除</Button>
            <button type="button" onClick={() => {
              setSelectedTaskIds([]);
              setSelectionAnchorId(null);
            }}>取消选择</button>
          </section>
        )}

        <div className="storyboard-scenes" data-testid="storyboard-scenes">
          {scenes.map((scene) => {
            const summary = sceneSummary(scene.id);
            return (
              <section
                key={scene.id}
                className={`storyboard-scene-section ${scene.id === selectedScene?.id ? "is-selected" : ""} ${dropTarget === `scene:${scene.id}` ? "is-drop-target" : ""}`}
                data-testid={`scene-section-${scene.id}`}
                onDragOver={(event) => {
                  if (draggedTaskIds.length === 0) return;
                  event.preventDefault();
                  setDropTarget(`scene:${scene.id}`);
                }}
                onDrop={(event) => {
                  if (draggedTaskIds.length === 0) return;
                  event.preventDefault();
                  moveTasks(draggedTaskIds, scene.id);
                }}
              >
                <header onClick={() => {
                  setSelectedSceneId(scene.id);
                  setSelectedTaskIds([]);
                  setSelectionAnchorId(null);
                }}>
                  <div>
                    <span>{scene.number}</span>
                    <h2>{scene.title || "未命名场景"}</h2>
                    <small><MapPin size={12} /> {scene.location || "地点待定"} · {scene.timeOfDay || "时间待定"}</small>
                  </div>
                  <p>{summary.tasks.length} Tasks · {summary.duration}s planned · {summary.running} Running · {summary.needsAttention} Needs Attention</p>
                </header>

                {summary.tasks.length > 0 ? (
                  <div className="storyboard-task-grid" role="listbox" aria-label={`${scene.number} Task Cards`}>
                    {summary.tasks.map((task) => (
                      <StoryboardTaskCard
                        key={task.id}
                        task={task}
                        primaryResultPreviewUrl={snapshot.results.find((result) => result.id === task.primaryResultId)?.previewUrl}
                        selected={selectedTaskIds.includes(task.id)}
                        onSelect={selectTask}
                        onOpen={openTaskComposer}
                        onDragStart={startTaskDrag}
                        onDragOver={(targetTask, event) => {
                          if (draggedTaskIds.length === 0 || draggedTaskIds.includes(targetTask.id)) return;
                          event.preventDefault();
                          event.stopPropagation();
                          setDropTarget(`task:${targetTask.id}`);
                        }}
                        onDrop={(targetTask, event) => {
                          if (draggedTaskIds.length === 0 || draggedTaskIds.includes(targetTask.id)) return;
                          event.preventDefault();
                          event.stopPropagation();
                          const placement = getTaskPlacement(snapshot, targetTask.id);
                          if (placement) moveTasks(draggedTaskIds, placement.sceneId, targetTask.id);
                        }}
                        onDragEnd={() => {
                          setDraggedTaskIds([]);
                          setDropTarget(null);
                        }}
                        dropTarget={dropTarget === `task:${task.id}`}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="storyboard-scene-empty">
                    <Film size={20} />
                    <span>此 Scene 还没有 Task Card</span>
                    <button type="button" onClick={() => createTask(false, scene.id)}>添加第一个 Task</button>
                  </div>
                )}
              </section>
            );
          })}
        </div>
      </section>

      {inspectorCollapsed ? (
        <div className="storyboard-collapsed-rail is-right">
          <button type="button" onClick={() => setInspectorCollapsed(false)} aria-label="展开 Inspector">
            <PanelRightOpen size={17} />
          </button>
        </div>
      ) : (
        <aside className="storyboard-inspector" aria-label="Inspector">
          <header>
            <div>
              <span className="eyebrow">{selectedTasks.length > 1 ? "BATCH" : selectedTask ? "TASK" : "SCENE OVERVIEW"}</span>
              <h2>{selectedTasks.length > 1 ? "Batch Inspector" : selectedTask ? "Task Inspector" : "Scene Overview"}</h2>
            </div>
            <button type="button" onClick={() => setInspectorCollapsed(true)} aria-label="折叠 Inspector">
              <PanelRightClose size={16} />
            </button>
          </header>

          {selectedTasks.length > 1 ? (
            <>
              <section>
                <span className="storyboard-inspector-number">MULTI SELECT</span>
                <h3>{selectedTasks.length} 个 Task</h3>
                <p>以下操作只作用于明确选中的生成任务，并显示实际处理结果。</p>
              </section>
              <section className="storyboard-metrics">
                <div><span>Tasks</span><strong>{selectedTasks.length}</strong></div>
                <div><span>Planned</span><strong>{selectedTasks.reduce((total, task) => total + task.plannedDurationSeconds, 0)}s</strong></div>
                <div><span>Protected</span><strong>{protectedDeleteCount}</strong></div>
              </section>
              <section className="storyboard-batch-actions" aria-label="Batch Inspector 操作">
                <label>
                  <span>移动到 Scene</span>
                  <PortalSelect
                    value={batchSceneId}
                    onChange={setBatchSceneId}
                    ariaLabel="批量移动目标 Scene"
                    options={scenes.map((scene) => ({ value: scene.id, label: `${scene.number} · ${scene.title}` }))}
                  />
                </label>
                <Button onClick={() => moveTasks(selectedTaskIds, batchSceneId)}>移动所选 Task</Button>
                <label>
                  <span>Generation Profile</span>
                  <PortalSelect
                    value={batchProfileId}
                    onChange={setBatchProfileId}
                    ariaLabel="批量 Generation Profile"
                    options={mockGenerationProfiles.map((profile) => ({ value: profile.id, label: profile.label, detail: profile.detail }))}
                  />
                </label>
                <Button onClick={applyBatchProfile}>应用 Profile</Button>
                <Button onClick={bindBatchAsset}>绑定雨声参考资产</Button>
                <Button onClick={queueBatch}>将 Ready Task 加入队列</Button>
                <Button onClick={duplicateSelectedTasks}><Copy size={14} /> 复制所选 Task</Button>
                <Button className="storyboard-danger-button" onClick={() => setDeleteDialogOpen(true)}>
                  <Trash2 size={14} /> 删除可删除项
                </Button>
              </section>
            </>
          ) : selectedTask ? (
            <>
              <section className="storyboard-task-inspector-form">
                <span className="storyboard-inspector-number">{selectedTask.number}</span>
                <div
                  className="storyboard-inspector-frame"
                  style={selectedTask.storyboardFrame.previewUrl ? { backgroundImage: `url("${selectedTask.storyboardFrame.previewUrl}")` } : undefined}
                  aria-label="Storyboard Frame"
                />
                <label>
                  <span>Task Name</span>
                  <input
                    aria-label="Task Name"
                    value={selectedTask.title}
                    onChange={(event) => setSnapshot((current) => updateTaskIntent(current, selectedTask.id, { title: event.target.value }))}
                  />
                </label>
                <label>
                  <span>Summary</span>
                  <textarea
                    aria-label="Task Summary"
                    rows={2}
                    value={selectedTask.summary}
                    onChange={(event) => setSnapshot((current) => updateTaskIntent(current, selectedTask.id, { summary: event.target.value }))}
                  />
                </label>
                <label>
                  <span>Script Source</span>
                  <textarea
                    aria-label="Inspector Script Source"
                    rows={3}
                    value={selectedTask.scriptSource}
                    onChange={(event) => setSnapshot((current) => updateTaskIntent(current, selectedTask.id, { scriptSource: event.target.value }))}
                  />
                </label>
                <label>
                  <span>User Intent</span>
                  <textarea
                    aria-label="Inspector User Intent"
                    rows={3}
                    value={selectedTask.userIntent}
                    onChange={(event) => setSnapshot((current) => updateTaskIntent(current, selectedTask.id, { userIntent: event.target.value }))}
                  />
                </label>
              </section>
              <section className="storyboard-metrics">
                <div><span>Visual Beats</span><strong>{selectedTask.visualBeats.length}</strong></div>
                <div><span>Planned</span><strong>{selectedTask.plannedDurationSeconds}s</strong></div>
                <div><span>Assets</span><strong>{selectedTask.assetBindings.length}</strong></div>
              </section>
              <Button onClick={() => setAssetPickerOpen(true)}>管理 Task 资产</Button>
              <section className="storyboard-inspector-fields">
                <label>
                  <span>Planned Duration</span>
                  <input
                    type="number"
                    min="0"
                    aria-label="Planned Duration"
                    value={selectedTask.plannedDurationSeconds}
                    onChange={(event) => setSnapshot((current) => updateTaskIntent(current, selectedTask.id, {
                      plannedDurationSeconds: Math.max(0, Number(event.target.value) || 0),
                    }))}
                  />
                </label>
                <label>
                  <span>Generation Profile</span>
                  <PortalSelect
                    value={selectedTask.generationProfileId}
                    onChange={(profileId) => {
                      const profile = getMockGenerationProfile(profileId);
                      setSnapshot((current) => updateTaskIntent(current, selectedTask.id, {
                        generationProfileId: profile.id,
                        generationProfileLabel: profile.label,
                      }));
                    }}
                    ariaLabel="Inspector Generation Profile"
                    options={mockGenerationProfiles.map((profile) => ({ value: profile.id, label: profile.label, detail: profile.detail }))}
                  />
                </label>
              </section>
              {selectedProfileWarnings.length > 0 && (
                <div className="storyboard-capability-warning" role="alert">
                  {selectedProfileWarnings.map((warning) => <p key={warning}>{warning}</p>)}
                </div>
              )}
              <section className="storyboard-beat-summary">
                <label>Visual Beats Summary</label>
                {selectedTask.visualBeats.length > 0 ? selectedTask.visualBeats.map((beat, index) => (
                  <div key={beat.id}><span>{index + 1}</span><p><strong>{beat.label}</strong><small>{beat.description}</small></p></div>
                )) : <p>尚未规划 Visual Beat。</p>}
              </section>
              {selectedTaskContexts.some((link) => link.stale) && (
                <p className="storyboard-context-warning" role="status">
                  Generation Context 已变化，请选择更新 Context、保留现有 Result 或重新生成。
                </p>
              )}
              <section className="storyboard-ready-panel" aria-label="Ready Validation">
                <header>
                  <label>Ready Validation</label>
                  <span className={selectedReadyIssues.length === 0 ? "is-pass" : "is-blocked"}>
                    {selectedReadyIssues.length === 0 ? "可生成" : `${selectedReadyIssues.length} 项待处理`}
                  </span>
                </header>
                <div className="storyboard-ready-checks">
                  {selectedReadyIssues.length === 0 ? (
                    <p>Final Prompt、Assets、Profile、时长、Beats、Context 与 Provider 均通过。</p>
                  ) : selectedReadyIssues.map((issue) => (
                    <p key={`${issue.code}-${issue.message}`}><strong>{issue.code}</strong>{issue.message}</p>
                  ))}
                </div>
                <div className="storyboard-ready-actions">
                  <Button onClick={runSelectedReadyValidation}>运行 Ready 校验</Button>
                  <Button
                    variant="accent"
                    onClick={queueSelectedTask}
                    disabled={selectedTask.state !== "ready" || !providerOnline}
                  >加入生成队列</Button>
                </div>
              </section>
              <section aria-label="Prompt 与执行">
                <label>Prompt / Execution</label>
                <div className="key-value"><span>State</span><strong>{selectedTask.state}</strong></div>
                <div className="key-value"><span>AI Prompt</span><strong>{selectedTask.aiPrompt ? "已有草稿" : "未生成"}</strong></div>
                <div className="key-value"><span>Final Prompt</span><strong>{selectedTask.finalPrompt ? "已确认" : "未确认"}</strong></div>
                <div className="key-value"><span>Context</span><strong>{selectedTaskContexts.length}</strong></div>
                <div className="key-value"><span>Jobs</span><strong>{selectedTask.jobIds.length}</strong></div>
                <div className="key-value"><span>Results</span><strong>{selectedTaskResults.length}</strong></div>
                <Button onClick={regenerateSelectedPrompt}>重编 AI Prompt</Button>
              </section>
              <section aria-label="Story Order 邻接">
                <label>Story Neighbors</label>
                <div className="key-value"><span>Previous</span><strong>{previousTask ? `${previousTask.number} · ${previousTask.title}` : "无"}</strong></div>
                <div className="key-value"><span>Next</span><strong>{nextTask ? `${nextTask.number} · ${nextTask.title}` : "无"}</strong></div>
                <div className="key-value"><span>Primary Result</span><strong>{selectedTask.primaryResultId ?? "无"}</strong></div>
              </section>
              <section className="storyboard-context-panel" aria-label="Generation Context">
                <header><label>Generation Context</label><small>Task 间生成依赖，不是 Story Order</small></header>
                {selectedTaskContexts.length > 0 ? selectedTaskContexts.map((link) => {
                  const isIncoming = link.targetTaskId === selectedTask.id;
                  const peerTaskId = isIncoming ? link.sourceTaskId : link.targetTaskId;
                  const peerTask = snapshot.tasks.find((task) => task.id === peerTaskId);
                  return (
                    <article key={link.id} className={link.stale ? "is-stale" : ""}>
                      <div><span>{isIncoming ? "来自" : "传给"}</span><strong>{peerTask ? `${peerTask.number} · ${peerTask.title}` : peerTaskId}</strong></div>
                      <p><em>{link.kind === "fallback" ? "Fallback · 已降级" : link.kind}</em><span>{link.stale ? "Context Stale" : link.sourceResultId ? `Result ${link.sourceResultId}` : "Semantic only"}</span></p>
                    </article>
                  );
                }) : <p>当前 Task 没有显式 Generation Context Link。</p>}
                <div className="storyboard-context-actions">
                  <Button onClick={refreshSelectedContext}>更新 Context</Button>
                  <Button
                    onClick={() => setOperationMessage("已保留现有 Result；Context Stale 标记不会被静默清除")}
                    disabled={!selectedTask.primaryResultId}
                  >保持现有 Result</Button>
                  <Button onClick={regenerateFromSelectedTask}>从此 Task 向后重新生成</Button>
                </div>
              </section>
              <Button onClick={() => openTaskComposer(selectedTask)}>打开完整 Task Composer</Button>
            </>
          ) : selectedScene && selectedSceneSummary ? (
            <>
              <section className="storyboard-scene-inspector-form">
                <span className="storyboard-inspector-number">{selectedScene.number}</span>
                <label><span>Scene Name</span><input aria-label="Scene Name" value={selectedScene.title} onChange={(event) => setSnapshot((current) => updateSceneMetadata(current, selectedScene.id, { title: event.target.value }))} /></label>
                <label><span>Summary</span><textarea aria-label="Scene Summary" rows={3} value={selectedScene.summary} onChange={(event) => setSnapshot((current) => updateSceneMetadata(current, selectedScene.id, { summary: event.target.value }))} /></label>
              </section>
              <section className="storyboard-metrics">
                <div><span>Tasks</span><strong>{selectedSceneSummary.tasks.length}</strong></div>
                <div><span>Planned</span><strong>{selectedSceneSummary.duration}s</strong></div>
                <div><span>Running</span><strong>{selectedSceneSummary.running}</strong></div>
              </section>
              <section>
                <label>场景信息</label>
                <label className="storyboard-inline-field"><span>地点</span><input aria-label="Scene Location" value={selectedScene.location} onChange={(event) => setSnapshot((current) => updateSceneMetadata(current, selectedScene.id, { location: event.target.value }))} /></label>
                <label className="storyboard-inline-field"><span>时间</span><input aria-label="Scene Time" value={selectedScene.timeOfDay} onChange={(event) => setSnapshot((current) => updateSceneMetadata(current, selectedScene.id, { timeOfDay: event.target.value }))} /></label>
                <label className="storyboard-inline-field"><span>Notes</span><textarea aria-label="Scene Notes" rows={3} value={selectedScene.notes} onChange={(event) => setSnapshot((current) => updateSceneMetadata(current, selectedScene.id, { notes: event.target.value }))} /></label>
              </section>
            </>
          ) : null}
        </aside>
      )}
    </div>
    <Dialog
      open={deleteDialogOpen}
      icon="delete" title={deletableTaskCount > 0 ? `删除 ${deletableTaskCount} 个 Task？` : "所选 Task 含历史记录，无法删除"}
      description={protectedDeleteCount > 0
        ? `${protectedDeleteCount} 个 Task 已有 Job 或 Result 历史，将被保留。`
        : "删除会移除当前 Task Card 及其 Story Order placement。"}
      onClose={() => setDeleteDialogOpen(false)}
    >
      <div className="storyboard-delete-dialog">
        <p>{deletableTaskCount > 0 ? "此操作不会修改其他 Task 的 Job 或 Result 历史。" : "请保留该 Task，或在后续版本中使用归档。"}</p>
        <div>
          <Button onClick={() => setDeleteDialogOpen(false)}>{deletableTaskCount > 0 ? "取消" : "知道了"}</Button>
          {deletableTaskCount > 0 && (
            <Button className="storyboard-danger-button" onClick={confirmDelete}>确认删除</Button>
          )}
        </div>
      </div>
    </Dialog>
    <ScriptToTasksDialog
      open={scriptDialogOpen}
      scenes={scenes}
      defaultSceneId={selectedScene?.id ?? scenes[0]?.id ?? ""}
      onClose={() => setScriptDialogOpen(false)}
      onAccept={acceptTaskProposals}
    />
    <AssetPickerDialog
      open={assetPickerOpen}
      assets={snapshot.assets}
      initialBindings={selectedTask?.assetBindings ?? []}
      onClose={() => setAssetPickerOpen(false)}
      onConfirm={(bindings) => {
        if (selectedTask) setSnapshot((current) => replaceTaskAssetBindings(current, selectedTask.id, bindings));
        setAssetPickerOpen(false);
        setOperationMessage(`已确认绑定 ${bindings.length} 项资产`);
      }}
    />
    </>
  );
}
