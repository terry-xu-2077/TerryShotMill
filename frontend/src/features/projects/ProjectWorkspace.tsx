import { VideoVersionSelect } from "./VideoVersionSelect";
import { GenerationProgress, TaskProgressLight } from "./GenerationProgress";
import { TaskRiskSticker } from "./TaskRiskSticker";
import { TaskNewResults, useViewedResults } from "./TaskNewResults";
import { TaskPreview } from "./TaskPreview";
import {
  LoaderCircle,
  Square,
  Grid2X2,
  Home,
  List,
  Play,
  Pencil,
  Plus,
  Sparkles,
  SlidersHorizontal,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import { Button, Checkbox } from "../../ui/primitives";

import {
  listTasksInStoryOrder,
  type GenerationTask,
  type Result,
  type StoryboardDomainSnapshot,
} from "../../domain/storyboard";
import type {
  PromptReviewItem,
  PromptBatchEligibility,
  VideoBatchEligibility,
  VideoBatchResponse,
} from "../../gateways/batchReviewGateway";
import type { ApplicationSettings } from "../../gateways/projectGateway";
import { taskSaveInput } from "../../gateways/projectGatewayMapper";
import type { DirectorProject } from "../../features/projects/projectTypes";
import type {
  PromptEnhancementRequest,
  PromptEnhancementResponse,
} from "../../services/promptEnhancement";
import { ContextMenu, Dialog, OverlayPortal, useOverlayZIndex } from "../../ui/overlay";
import { TaskEditorDialog } from "../storyboard/TaskEditorDialog";
import { updateTaskComposerFields } from "../storyboard/storyboardMutations";
import {
  BatchPromptDialog,
  BatchVideoDialog,
  type PromptBatchOptions,
} from "./BatchReviewControls";
import { ProjectConfigPanel } from "./ProjectConfigPanel";
import { useTaskViewMode } from "./useTaskViewMode";
import { ThemeSwitch } from "../../ui/ThemeSwitch";
import { TaskResultPlayer } from "./TaskResultPlayer";
import { formatElapsed, taskTimeSummary, useLiveTaskTimings } from "./taskTiming";




type DisplayStatus = "idle" | "enhancing" | "queued" | "running" | "completed" | "failed";
type TaskEditorPatch = Partial<Pick<GenerationTask,
  "title" | "aiPrompt" | "finalPrompt" | "generationParams" | "plannedDurationSeconds" | "assetBindings"
>>;
type ProjectSettingsPatch = Pick<DirectorProject, "title" | "description" | "useDescriptionForAiPrompt">;
type BatchPromptSubmit = (request: {
  taskIds: string[];
  includeProjectBackground: boolean;
  includePreviousTaskSummary: boolean;
}) => Promise<unknown>;

const taskStatusLabel: Record<DisplayStatus, string> = {
  idle: "未开始",
  enhancing: "增强中",
  queued: "排队中",
  running: "生成中",
  completed: "已完成",
  failed: "失败",
};

function displayTaskStatus(task: GenerationTask): DisplayStatus {
  if (task.state === "prompt-generating") return "enhancing";
  if (task.state === "completed") return "completed";
  if (task.state === "running" || task.state === "queued") return task.state;
  if (task.state === "failed") return "failed";
  return "idle";
}

function orderedTasks(snapshot: StoryboardDomainSnapshot) {
  return snapshot.scenes
    .slice()
    .sort((left, right) => left.orderKey.localeCompare(right.orderKey))
    .flatMap((scene) => listTasksInStoryOrder(snapshot, scene.id));
}

function taskResult(snapshot: StoryboardDomainSnapshot, task: GenerationTask) {
  const primary = task.primaryResultId
    ? snapshot.results.find((result) => result.id === task.primaryResultId)
    : undefined;
  if (primary) return primary;
  const jobIds = new Set(snapshot.jobs.filter((job) => job.taskId === task.id).map((job) => job.id));
  return snapshot.results.slice().reverse().find((result) => result.videoUrl && jobIds.has(result.jobId));
}

function taskPreview(snapshot: StoryboardDomainSnapshot, task: GenerationTask) {
  return taskResult(snapshot, task)?.previewUrl;
}

function resultCount(snapshot: StoryboardDomainSnapshot, taskId: string) {
  const jobIds = new Set(snapshot.jobs.filter((job) => job.taskId === taskId).map((job) => job.id));
  return snapshot.results.filter((result) => jobIds.has(result.jobId)).length;
}

function generationSummary(task: GenerationTask) {
  const params = task.generationParams ?? {};
  return [params.resolution ? `分辨率：${String(params.resolution).toUpperCase()}` : null,
    task.plannedDurationSeconds ? `时长：${task.plannedDurationSeconds} 秒` : null,
    params.quality ? `质量：${String(params.quality)}` : null,
    `提示词：${params.promptSource === "ai" ? "AI" : params.promptSource === "user" ? "用户" : "读取中"}`].filter(Boolean).join(" · ") || "未设置生成参数";
}

function promptSummary(task: GenerationTask) {
  return task.finalPrompt || task.userIntent || task.summary || "还没有提示词";
}

function makeDraftTask(snapshot: StoryboardDomainSnapshot): GenerationTask {
  const serial = snapshot.tasks.length + 1;
  return {
    id: `task-local-${Date.now()}`,
    number: `T01-${String(serial).padStart(3, "0")}`,
    title: `新任务 ${serial}`,
    summary: "",
    scriptSource: "",
    userIntent: "",
    storyboardFrame: { sourceType: "placeholder", updatedAt: new Date().toISOString() },
    visualBeats: [],
    assetBindings: [],
    plannedDurationSeconds: 6,
    generationProfileId: "profile-h3-multi-shot",
    generationProfileLabel: "H3",
    aiPrompt: "",
    finalPrompt: "",
    promptRevisions: [],
    generationParams: {
      aspectRatio: "16:9",
      resolution: "1080p",
      quality: "标准",
      generationMode: "全能参考",
      contextMode: "尾帧承接",
      promptSource: "user",
      userPromptViewMode: "visual",
      aiPromptViewMode: "visual",
    },
    contextLinkIds: [],
    state: "draft",
    jobIds: [],
  };
}

function TaskInfoPanel({ history, snapshot, task, review, onPlayResult, timing, actions, newKinds, warnings, statusNote }: {
  statusNote?: string | null;
  newKinds: ("video" | "prompt")[];
  warnings: string[];
  actions?: ReactNode;
  timing?: import("../../gateways/projectGateway").TaskTiming;
  history?: ReactNode;
  snapshot: StoryboardDomainSnapshot;
  task?: GenerationTask;
  review?: PromptReviewItem;
  onPlayResult: (result: Result, task: GenerationTask) => void;
}) {
  if (!task) return <aside className="project-task-info" aria-label="任务信息"><div className="project-task-info-empty">选择一个任务查看信息</div></aside>;
  const params = task.generationParams ?? {};
  const status = displayTaskStatus(task);
  const result = taskResult(snapshot, task);
  const preview = taskPreview(snapshot, task);
  return (
    <aside className="project-task-info" aria-label="任务信息">
      <div className="task-info-preview">
      {result ? <button type="button" className="task-result-preview-button" onClick={() => onPlayResult(result, task)} aria-label={`播放任务 ${task.title} 的生成结果`}><TaskPreview previewUrl={preview} /><span className="task-result-play"><Play size={25} fill="currentColor" /></span></button> : <TaskPreview previewUrl={preview} />}
        <div className="task-info-notices"><TaskNewResults kinds={newKinds} /><TaskRiskSticker key={task.id} warnings={warnings} /></div>
      </div>
      {actions}
      {history}
      <h2>任务名：{task.title}</h2>
      <section className="project-info-block"><h3>提示词</h3><p>{promptSummary(task)}</p></section>
      <GenerationProgress timing={timing} status={statusNote ?? taskStatusLabel[status]} />
      <section className="project-info-block">
        <h3>生成参数</h3>
        <dl>
          <div><dt>提示词</dt><dd className={`task-review-inline is-${review?.promptReviewStatus ?? "pending_review"}`}>{review?.promptReviewStatus === "approved" ? "已检查" : "待检查"}</dd></div>
          <div><dt>计划时长</dt><dd>{task.plannedDurationSeconds || 0} 秒</dd></div>
          <div><dt>{timing?.promptRunning ? "增强已用时" : "最近增强耗时"}</dt><dd>{formatElapsed(timing?.promptSeconds)}</dd></div>
          {timing?.promptQueueSeconds != null && <div><dt>增强排队耗时</dt><dd>{formatElapsed(timing.promptQueueSeconds)}</dd></div>}
          <div><dt>{timing?.videoRunning ? "生成已用时" : "最近生成耗时"}</dt><dd>{formatElapsed(timing?.videoSeconds)}</dd></div>
          <div><dt>视频排队耗时</dt><dd>{formatElapsed(timing?.videoQueueSeconds)}</dd></div>
          <div><dt>目标分辨率</dt><dd>{String(params.resolution ?? "1080P").toUpperCase()}</dd></div>
          <div><dt>质量</dt><dd>{String(params.quality ?? "标准")}</dd></div>
        </dl>
      </section>
    </aside>
  );
}

export function ProjectWorkspace({
  bridgeStatus,
  project,
  promptReviewItems,
  onStopVideoJob,
  onVideoVersionChanged,
  onBack,
  onLoadTaskEditor,
  onCreateTask,
  onUpdateTask,
  onUpdateEditorPreference,
  onSaveProjectConfiguration,
  onEnhancePrompt,
  onBatchEnhancePrompts,
  onCheckPromptBatchEligibility,
  onCheckVideoBatchEligibility,
  onCreateVideoBatch,
  applicationSettings,
  onRefreshComfyUIWorkflows,
}: {
  bridgeStatus?: ReactNode;
  project: DirectorProject;
  promptReviewItems: PromptReviewItem[];
  onVideoVersionChanged?: () => Promise<void>;
  onStopVideoJob?: (jobId: string) => Promise<void>;
  onBack: () => void;
  onLoadTaskEditor: (taskId: string) => Promise<GenerationTask>;
  onCreateTask: (task: GenerationTask) => Promise<string>;
  onUpdateTask: (task: GenerationTask) => Promise<void>;
  onUpdateEditorPreference?: (taskId: string, preference: Partial<import("../../gateways/projectGateway").TaskEditorView["editorPreference"]>) => Promise<void>;
  onSaveProjectConfiguration: (settings: ProjectSettingsPatch, assets: DirectorProject["snapshot"]["assets"]) => Promise<void>;
  onEnhancePrompt: (request: PromptEnhancementRequest) => Promise<PromptEnhancementResponse>;
  onBatchEnhancePrompts: BatchPromptSubmit;
  onCheckPromptBatchEligibility: (taskIds: string[]) => Promise<PromptBatchEligibility>;
  onCancelPromptBatch: (batchId: string) => Promise<void>;
  onCancelQueuedVideos?: (jobIds: string[]) => Promise<void>;
  onRetryFailedPromptBatch: (batchId: string) => Promise<void>;
  onApprovePrompt: (taskId: string) => Promise<PromptReviewItem>;
  onCheckVideoBatchEligibility: (taskIds: string[]) => Promise<VideoBatchEligibility>;
  onCreateVideoBatch: (taskIds: string[]) => Promise<VideoBatchResponse>;
  applicationSettings?: ApplicationSettings;
  onSaveApplicationSettings: (settings: ApplicationSettings) => Promise<void>;
  onRefreshComfyUIWorkflows: () => Promise<import("../../gateways/projectGateway").ComfyUIWorkflow[]>;
}) {
  const [viewMode, setViewMode] = useTaskViewMode(project.id);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [batchSelectedTaskIds, setBatchSelectedTaskIds] = useState<Set<string>>(() => new Set());
  const [managingTasks, setManagingTasks] = useState(false);
  const [batchAnchorIndex, setBatchAnchorIndex] = useState<number | null>(null);
  const [batchPromptOpen, setBatchPromptOpen] = useState(false);
  const [batchPromptBusy, setBatchPromptBusy] = useState(false);
  const [batchPromptError, setBatchPromptError] = useState("");
  const [promptEligibility, setPromptEligibility] = useState<PromptBatchEligibility>();
  const [promptEligibilityLoading, setPromptEligibilityLoading] = useState(false);
  const promptRequestVersion = useRef(0);
  const [promptRequestIds, setPromptRequestIds] = useState<string[]>([]);
  const [batchVideoOpen, setBatchVideoOpen] = useState(false);
  const [batchVideoLoading, setBatchVideoLoading] = useState(false);
  const [batchVideoSubmitting, setBatchVideoSubmitting] = useState(false);
  const [batchVideoEligibility, setBatchVideoEligibility] = useState<VideoBatchEligibility>();
  const [videoRequestIds, setVideoRequestIds] = useState<string[]>([]);
  const [videoRequestMode, setVideoRequestMode] = useState<"single" | "queue">("queue");
  const [videoError, setVideoError] = useState("");
  const videoRequestVersion = useRef(0);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [loadedEditingTask, setLoadedEditingTask] = useState<GenerationTask | null>(null);
  const [draftTask, setDraftTask] = useState<GenerationTask | null>(null);
  const [projectConfigOpen, setProjectConfigOpen] = useState(false);
  const [playing, setPlaying] = useState<{ result: Result; task: GenerationTask } | null>(null);

  const { unread, markViewed } = useViewedResults();
  useEffect(() => { if (playing) markViewed("video", playing.result.id); }, [playing, markViewed]);
  const tasks = useMemo(() => orderedTasks(project.snapshot), [project.snapshot]);
  const timings = useLiveTaskTimings(project.taskTimings);
  const reviews = useMemo(() => new Map(promptReviewItems.map((item) => [item.taskId, item])), [promptReviewItems]);
  const selectedTask = tasks.find((task) => task.id === selectedTaskId);
  const editingTask = draftTask ?? loadedEditingTask;
  const editingTaskIndex = editingTask && !draftTask ? tasks.findIndex((task) => task.id === editingTask.id) : -1;
  const editingTaskState = tasks[editingTaskIndex]?.state ?? editingTask?.state;
  const previousEditingTask = draftTask ? tasks.at(-1) : editingTaskIndex > 0 ? tasks[editingTaskIndex - 1] : undefined;
  const savedPreviousDuration = editingTask?.generationParams.previousTaskDurationSeconds;
  const previousResultDuration = project.snapshot.results.find(
    (result) => result.id === previousEditingTask?.primaryResultId,
  )?.metadata.durationSeconds;
  const previousTaskDurationSeconds = typeof previousResultDuration === "number"
    ? previousResultDuration : typeof savedPreviousDuration === "number"
      ? savedPreviousDuration : previousEditingTask?.plannedDurationSeconds ?? 0;
  const previousTaskSummary = previousEditingTask ? previousEditingTask.summary.trim() || previousEditingTask.userIntent.trim() || previousEditingTask.title : "";
  const selectedIdsInOrder = tasks.filter((task) => batchSelectedTaskIds.has(task.id)).map((task) => task.id);

  const actionIds = managingTasks ? selectedIdsInOrder : selectedTask ? [selectedTask.id] : [];


  const actionLayer = useOverlayZIndex(10);

  useEffect(() => {
    if (selectedTaskId && tasks.some((task) => task.id === selectedTaskId)) return;
    setSelectedTaskId(null);
  }, [selectedTaskId, tasks]);
  useEffect(() => {
    const validIds = new Set(tasks.map((task) => task.id));
    setBatchSelectedTaskIds((current) => new Set([...current].filter((id) => validIds.has(id))));
  }, [tasks]);

  useEffect(() => {
    const selectAll = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey || event.key.toLowerCase() !== "a") return;
      const target = event.target;
      if (target instanceof Element && target.closest('input, textarea, select, [contenteditable="true"], [role="textbox"]')) return;
      const openOverlay = [...document.querySelectorAll('dialog[open], [role="dialog"], [role="alertdialog"]')]
        .some(element => !element.closest('[inert], [aria-hidden="true"], dialog:not([open])'));
      if (openOverlay) return;
      event.preventDefault();
      window.getSelection()?.removeAllRanges();
      setManagingTasks(true);
      setBatchSelectedTaskIds(new Set(tasks.map(task => task.id)));
    };
    window.addEventListener("keydown", selectAll);
  return () => window.removeEventListener("keydown", selectAll);
  }, [tasks]);

  const openExistingEditor = async (taskId: string) => {
    setSelectedTaskId(taskId);
    setDraftTask(null);
    try {
      const task = await onLoadTaskEditor(taskId);
      setEditingTaskId(taskId);
      setLoadedEditingTask(task);
    } catch (error) { console.error("Failed to load task editor", error); }
  };
  const openNewTask = () => { setDraftTask(makeDraftTask(project.snapshot)); setEditingTaskId(null); setLoadedEditingTask(null); };
  const closeEditor = () => { setDraftTask(null); setEditingTaskId(null); setLoadedEditingTask(null); };

  const handleTaskSelection = (event: ReactMouseEvent<HTMLButtonElement>, taskId: string, index: number) => {
    setSelectedTaskId(taskId);
    if (event.shiftKey && batchAnchorIndex !== null) {
      setManagingTasks(true);
      const start = Math.min(batchAnchorIndex, index);
      const end = Math.max(batchAnchorIndex, index);
      setBatchSelectedTaskIds(new Set(tasks.slice(start, end + 1).map((task) => task.id)));
      return;
    }
    if (managingTasks || event.ctrlKey || event.metaKey) {
      setManagingTasks(true);
      setBatchAnchorIndex(index);
      setBatchSelectedTaskIds((current) => { const next = new Set(current); if (next.has(taskId)) next.delete(taskId); else next.add(taskId); return next; });
      return;
    }
    setBatchAnchorIndex(index);
    setBatchSelectedTaskIds(new Set());
  };
  const playTask = (task: GenerationTask) => {
    const result = taskResult(project.snapshot, task);
    if (result?.videoUrl) { setSelectedTaskId(task.id); setPlaying({ result, task }); }
  };
  const clearBatchSelection = () => { setBatchSelectedTaskIds(new Set()); setBatchAnchorIndex(null); setSelectedTaskId(null); };

  const toggleBatchTask = (taskId: string, index: number, checked: boolean) => {
    setSelectedTaskId(taskId);
    setBatchAnchorIndex(index);
    setBatchSelectedTaskIds((current) => {
      const next = new Set(current);
      if (checked) next.add(taskId); else next.delete(taskId);
      return next;
    });
  };
  const loadPromptEligibility = async (ids: string[]) => {
    const version = ++promptRequestVersion.current;
    setPromptEligibility(undefined);
    setPromptEligibilityLoading(true);
    setBatchPromptError("");
    try {
      const result = await onCheckPromptBatchEligibility(ids);
      if (version === promptRequestVersion.current) setPromptEligibility(result);
    } catch {
      if (version === promptRequestVersion.current) setBatchPromptError("任务状态检查失败，请重试。");
    } finally {
      if (version === promptRequestVersion.current) setPromptEligibilityLoading(false);
    }
  };
  const closePromptBatch = () => {
    if (batchPromptBusy) return;
    promptRequestVersion.current += 1;
    setBatchPromptOpen(false);
  };
  const openPromptBatch = () => {
    const ids = selectedIdsInOrder.length ? [...selectedIdsInOrder] : tasks.map((task) => task.id);
    setPromptRequestIds(ids);
    setBatchPromptOpen(true);
    void loadPromptEligibility(ids);
  };

  const submitBatchPromptEnhancement = async (options: PromptBatchOptions) => {
    if (!promptEligibility?.eligibleTaskIds.length || batchPromptBusy || promptEligibilityLoading) return;
    setBatchPromptBusy(true);
    setBatchPromptError("");
    let submissionStarted = false;
    try {
      const current = await onCheckPromptBatchEligibility(promptRequestIds);
      setPromptEligibility(current);
      if (JSON.stringify(current.eligibleTaskIds) !== JSON.stringify(promptEligibility.eligibleTaskIds)) {
        setBatchPromptError("任务状态已变化，已更新可增强数量，请重新确认。");
        return;
      }
      submissionStarted = true;
      await onBatchEnhancePrompts({ taskIds: current.eligibleTaskIds, includeProjectBackground: options.includeProjectBackground, includePreviousTaskSummary: options.includePreviousTaskSummary });
      setBatchPromptOpen(false);
    } catch { setBatchPromptError(submissionStarted ? "增强提交未确认，请取消并检查任务状态后重试。" : "任务状态检查失败，请重新检查后重试。"); }
    finally { setBatchPromptBusy(false); }
  };

  const updatedTaskFromPatch = (patch: TaskEditorPatch) => {
    if (!editingTaskId || !editingTask) return undefined;
    const { title, plannedDurationSeconds, ...composerPatch } = patch;
    const next = updateTaskComposerFields(
      { ...project.snapshot, tasks: project.snapshot.tasks.map((task) => task.id === editingTaskId ? editingTask : task) },
      editingTaskId,
      composerPatch,
    );
    const updated = next.tasks.find((task) => task.id === editingTaskId);
    return updated ? { ...updated, ...(typeof title === "string" && title.trim() ? { title: title.trim() } : {}), ...(typeof plannedDurationSeconds === "number" ? { plannedDurationSeconds } : {}) } : undefined;
  };

  const saveTask = async (patch: TaskEditorPatch) => {
    if (draftTask) {
      const finalPrompt = patch.finalPrompt ?? draftTask.finalPrompt;
      const savedTask: GenerationTask = { ...draftTask, ...patch, summary: finalPrompt.trim() || draftTask.summary, generationParams: { ...draftTask.generationParams, ...(patch.generationParams ?? {}) } };
      const taskId = await onCreateTask(savedTask);
      setSelectedTaskId(taskId);
      return;
    }
    const updated = updatedTaskFromPatch(patch);
    if (updated) await onUpdateTask(updated);
  };

  const closeVideoBatch = () => {
    if (batchVideoSubmitting) return;
    videoRequestVersion.current += 1;
    setBatchVideoOpen(false);
    setBatchVideoLoading(false);
  };
  const openVideoBatch = async (taskIds = selectedIdsInOrder, mode: "single" | "queue" = "queue") => {
    if (!taskIds.length || batchVideoSubmitting || batchVideoLoading) return;
    const version = ++videoRequestVersion.current;
    const requestedIds = [...taskIds];
    setVideoRequestIds(requestedIds);
    setVideoRequestMode(mode);
    setVideoError("");
    setBatchVideoOpen(mode !== "single");
    setBatchVideoEligibility(undefined);
    setBatchVideoLoading(true);
    try {
      const eligibility = await onCheckVideoBatchEligibility(requestedIds);
      if (version !== videoRequestVersion.current) return;
      setBatchVideoEligibility(eligibility);
      if (mode === "single" && eligibility.eligibleTaskIds.length === requestedIds.length && !eligibility.skipped.length && !eligibility.warnings?.length) {
        await submitVideoBatch(eligibility);
      } else {
        setBatchVideoOpen(true);
      }
    } catch {
      if (version === videoRequestVersion.current) { setVideoError("无法检查生成条件，请取消后重试。"); setBatchVideoOpen(true); }
    } finally {
      if (version === videoRequestVersion.current) setBatchVideoLoading(false);
    }
  };
  const submitVideoBatch = async (eligibility = batchVideoEligibility) => {
    if (!eligibility?.eligibleTaskIds.length || batchVideoSubmitting) return;
    setBatchVideoSubmitting(true);
    setVideoError("");
    try {
      const result = await onCreateVideoBatch([...eligibility.eligibleTaskIds]);
      if (!result.eligibleTaskIds.length) {
        setBatchVideoEligibility(result);
        setVideoError("任务状态已变化，本次未提交，请检查下方原因。");
        setBatchVideoOpen(true);
        return;
      }
      setBatchVideoOpen(false);
      setBatchSelectedTaskIds(new Set());
      setBatchAnchorIndex(null);
    } catch { setVideoError("生成提交未确认，请取消并检查任务状态后重试。"); setBatchVideoOpen(true); }
    finally { setBatchVideoSubmitting(false); }
  };

  const activeVideo = project.runtime?.videoJobs?.find(job => job.taskId === selectedTaskId && job.state === "running");
  const [stopConfirm, setStopConfirm] = useState<string | null>(null);
  const [stoppingJobs, setStoppingJobs] = useState<Set<string>>(() => new Set());
  const [stopError, setStopError] = useState("");
  const stopping = !!activeVideo && (stoppingJobs.has(activeVideo.id) || !!timings[selectedTaskId ?? ""]?.generationProgress?.stopRequested);
  const confirmStop = async () => {
    const id = stopConfirm;
    setStopConfirm(null);
    if (!id || !onStopVideoJob) return;
    setStoppingJobs(current => new Set(current).add(id));
    setStopError("");
    try { await onStopVideoJob(id); }
    catch { setStoppingJobs(current => { const next = new Set(current); next.delete(id); return next; }); setStopError("停止请求未确认，请重试。任务可能仍在运行。"); }
  };
  const taskActions = managingTasks || actionIds.length ? (
    <div className={`task-context-actions is-visible${managingTasks ? "" : " is-single"}`} role="region" aria-label="任务操作">
      {managingTasks && <strong>已选 {actionIds.length} 项</strong>}
      {managingTasks ? <>
        <div className="task-action-group" role="group" aria-label="生成操作">
          <Button disabled={!actionIds.length || batchPromptBusy} onClick={openPromptBatch}><Sparkles size={15} />增强提示词</Button>
          <Button variant="accent" disabled={!actionIds.length || batchVideoLoading || batchVideoSubmitting} onClick={() => void openVideoBatch(actionIds, "queue")}>{batchVideoLoading || batchVideoSubmitting ? <><LoaderCircle className="task-stop-spinner" size={15} />正在提交</> : <><Play size={15} />生成视频</>}</Button>
        </div>
        <div className="task-action-group is-selection" role="group" aria-label="选择操作">
          <Button disabled={!tasks.length || actionIds.length === tasks.length} onClick={() => setBatchSelectedTaskIds(new Set(tasks.map(task => task.id)))}>全选</Button>
          <Button disabled={!actionIds.length} onClick={clearBatchSelection}>取消选择</Button>
        </div>
      </> : <>
        <Button onClick={() => actionIds[0] && void openExistingEditor(actionIds[0])}><Pencil size={15} />编辑任务</Button>
        {activeVideo ? <Button disabled={stopping || !onStopVideoJob} onClick={() => setStopConfirm(activeVideo.id)}>{stopping ? <LoaderCircle className="task-stop-spinner" size={15} /> : <Square size={15} />}{stopping ? "正在停止" : "停止任务"}</Button> : <Button variant="accent" disabled={batchVideoLoading || batchVideoSubmitting} onClick={() => void openVideoBatch(actionIds, "single")}>{batchVideoLoading || batchVideoSubmitting ? <><LoaderCircle className="task-stop-spinner" size={15} />正在提交</> : <><Play size={15} />生成视频</>}</Button>}
      </>}
    </div>
  ) : undefined;
  return (
    <main className="project-workspace-page" aria-label="项目工作台">
      <header className="project-workspace-topbar">
        <div className="workspace-navigation">
          <Button onClick={onBack} aria-label="返回项目首页"><Home size={16} /><span className="workspace-home-label">返回首页</span></Button>
          <Button onClick={() => setProjectConfigOpen(true)}><SlidersHorizontal size={16} strokeWidth={1.6} />项目配置</Button>
        </div>
        <div className="workspace-project-title"><strong>{project.title}</strong></div>
        <div className="workspace-top-actions">
          {bridgeStatus}
          <ThemeSwitch />
        </div>
      </header>

      <div className="project-workspace-body">
        <div className="project-task-column">
        <section className="project-task-area" aria-label="任务区域">
          <header className="task-collection-heading">
            <h2>任务</h2>
            <div className="task-view-control">
              <Button size="icon" aria-label={viewMode === "list" ? "切换为卡片视图" : "切换为表格视图"} title={viewMode === "list" ? "切换为卡片视图" : "切换为表格视图"} aria-pressed={viewMode === "card"} onClick={() => setViewMode(viewMode === "list" ? "card" : "list")}>
                <span className={`task-view-glyph is-${viewMode}`} aria-hidden="true"><span className="task-view-list-icon"><List size={16} strokeWidth={1.6} /></span><span className="task-view-grid-icon"><Grid2X2 size={16} strokeWidth={1.6} /></span></span>
              </Button>
            </div>
            <Button disabled={!tasks.length} aria-pressed={managingTasks} onClick={() => { setManagingTasks(!managingTasks); clearBatchSelection(); }}>{managingTasks ? "完成管理" : "管理任务"}</Button>

          </header>
          {viewMode === "list" ? (
            <div key="list" className="task-list-view">
              <button type="button" className="task-list-row is-create" onClick={openNewTask} aria-label="新建任务卡"><div className="task-preview is-compact"><Plus className="creation-motion-icon" size={24} /></div><div className="task-list-copy"><strong>新建任务卡</strong></div><div className="task-list-stats"><span>{tasks.length} 个任务</span></div><div className="task-list-status"><Plus size={14} />新建</div></button>
              {tasks.map((task, index) => {
                const newKinds = unread(project.taskNewResults?.[task.id]);
                const warnings = project.taskWarnings?.[task.id] ?? [];
                const versions = resultCount(project.snapshot, task.id);
                const batchSelected = batchSelectedTaskIds.has(task.id);
                const reviewed = reviews.get(task.id)?.promptReviewStatus === "approved";
                const playable = Boolean(taskResult(project.snapshot, task)?.videoUrl);
                const elapsed = taskTimeSummary(timings[task.id]);
                return <ContextMenu key={task.id} actions={[{ label: task.state === "queued" || task.state === "running" ? "查看任务" : "编辑任务", onSelect: () => openExistingEditor(task.id) }]}><div className="task-collection-item is-list">{managingTasks && <div className="task-selection-control"><Checkbox checked={batchSelected} ariaLabel={`选择任务 · ${task.title}`} onChange={(checked) => toggleBatchTask(task.id, index, checked)} /></div>}<div className="task-item-content"><button type="button" className={`task-list-row ${selectedTaskId === task.id ? "is-selected" : ""} ${batchSelected ? "is-batch-selected" : ""}`} onClick={(event) => handleTaskSelection(event, task.id, index)} onDoubleClick={() => openExistingEditor(task.id)}><TaskPreview previewUrl={taskPreview(project.snapshot, task)} compact /><div className="task-list-copy"><div className="task-list-heading"><strong>#{index + 1} {task.title}</strong>{!newKinds.length && !warnings.length && <span className="task-plain-status"><i className={`workspace-status-dot is-${displayTaskStatus(task)}`} />{project.taskGenerationNotes?.[task.id] ?? taskStatusLabel[displayTaskStatus(task)]}</span>}</div><span className="task-list-params">{generationSummary(task)}</span></div><div className="task-list-stats"><span>{task.assetBindings.length} 个资产 · {versions > 0 ? `${versions} 个版本` : "无结果"} · {reviewed ? "已检查" : "待检查"}</span>{elapsed && <span className="task-elapsed">{elapsed}</span>}</div><TaskNewResults kinds={newKinds} /><TaskProgressLight timing={timings[task.id]} /></button><TaskRiskSticker warnings={warnings} />{playable && <button type="button" className="task-thumbnail-play" aria-label={`播放视频 · ${task.title}`} onClick={() => playTask(task)}><Play size={20} fill="currentColor" /></button>}</div></div></ContextMenu>;
              })}
            </div>
          ) : (
            <div key="card" className="task-card-view">
              <button type="button" className="task-create-card" onClick={openNewTask}><div><Plus className="creation-motion-icon" size={46} /></div><strong>新建任务卡</strong></button>
              {tasks.map((task, index) => {
                const newKinds = unread(project.taskNewResults?.[task.id]);
                const warnings = project.taskWarnings?.[task.id] ?? [];
                const versions = resultCount(project.snapshot, task.id);
                const batchSelected = batchSelectedTaskIds.has(task.id);
                const reviewed = reviews.get(task.id)?.promptReviewStatus === "approved";
                const playable = Boolean(taskResult(project.snapshot, task)?.videoUrl);
                const elapsed = taskTimeSummary(timings[task.id]);
                return <ContextMenu key={task.id} actions={[{ label: task.state === "queued" || task.state === "running" ? "查看任务" : "编辑任务", onSelect: () => openExistingEditor(task.id) }]}><div className="task-collection-item is-card">{managingTasks && <div className="task-selection-control"><Checkbox variant="media" checked={batchSelected} ariaLabel={`选择任务 · ${task.title}`} onChange={(checked) => toggleBatchTask(task.id, index, checked)} /></div>}<div className="task-item-content"><button type="button" className={`task-card-item ${selectedTaskId === task.id ? "is-selected" : ""} ${batchSelected ? "is-batch-selected" : ""}`} onClick={(event) => handleTaskSelection(event, task.id, index)} onDoubleClick={() => openExistingEditor(task.id)}><div className="task-card-preview-wrap"><TaskPreview previewUrl={taskPreview(project.snapshot, task)} /><TaskNewResults kinds={newKinds} /></div><div className="task-card-heading"><strong>#{index + 1} {task.title}</strong>{!newKinds.length && !warnings.length && <span className="task-plain-status"><i className={`workspace-status-dot is-${displayTaskStatus(task)}`} />{project.taskGenerationNotes?.[task.id] ?? taskStatusLabel[displayTaskStatus(task)]}</span>}</div><p>{generationSummary(task)}</p><footer>{reviewed ? "已检查" : "待检查"} · 使用{task.assetBindings.length}个资产 · {versions > 0 ? `${versions}个生成版本` : "无生成结果"}{elapsed && <div className="task-elapsed">{elapsed}</div>}</footer><TaskProgressLight timing={timings[task.id]} /></button><TaskRiskSticker warnings={warnings} />{playable && <button type="button" className="task-thumbnail-play" aria-label={`播放视频 · ${task.title}`} onClick={() => playTask(task)}><Play size={20} fill="currentColor" /></button>}</div></div></ContextMenu>;
              })}
            </div>
          )}
        </section>
        {(managingTasks || actionIds.length > 0) && <OverlayPortal><div className={`task-action-dock${!managingTasks ? " is-mobile-single" : ""}`} style={actionLayer}>{taskActions}</div></OverlayPortal>}
        </div>

        <TaskInfoPanel history={selectedTask ? <VideoVersionSelect key={selectedTask.id} projectId={project.id} taskId={selectedTask.id} resultId={selectedTask.primaryResultId} onChanged={onVideoVersionChanged} /> : undefined} statusNote={selectedTask ? project.taskGenerationNotes?.[selectedTask.id] : undefined} newKinds={unread(selectedTask ? project.taskNewResults?.[selectedTask.id] : undefined)} warnings={selectedTask ? project.taskWarnings?.[selectedTask.id] ?? [] : []} actions={!managingTasks && actionIds.length === 1 ? taskActions : undefined} snapshot={project.snapshot} task={selectedTask} timing={selectedTask ? timings[selectedTask.id] : undefined} review={selectedTask ? reviews.get(selectedTask.id) : undefined} onPlayResult={(result, task) => setPlaying({ result, task })} />
      </div>


      {stopError && <Dialog open icon="warning" title="停止任务失败" onClose={() => setStopError("")}><p>{stopError}</p><Button onClick={() => setStopError("")}>知道了</Button></Dialog>}
      <Dialog open={!!stopConfirm} icon="warning" title="停止任务" onClose={() => setStopConfirm(null)}><p>确定停止这个任务吗？本次未完成的生成将中止，已有结果会保留。</p><div className="task-stop-confirm-actions"><Button onClick={() => setStopConfirm(null)}>继续运行</Button><Button variant="accent" onClick={() => void confirmStop()}>确认停止</Button></div></Dialog>
      <TaskEditorDialog
        readOnly={!draftTask && (editingTaskState === "queued" || editingTaskState === "running")}
        workflowProfiles={applicationSettings?.comfyui.workflowProfiles}
        defaultWorkflowProfileId={applicationSettings?.comfyui.defaultProfileId}
        onLoadWorkflows={onRefreshComfyUIWorkflows}
        onViewPromptRevision={id => markViewed("prompt", id)}
        onUpdateEditorPreference={onUpdateEditorPreference}
        open={Boolean(editingTask)} task={editingTask ?? undefined} assets={project.snapshot.assets}
        previousTaskDurationSeconds={previousTaskDurationSeconds} previousTaskId={previousEditingTask?.id} previousTaskSummary={previousTaskSummary}
        isNewTask={Boolean(draftTask)} reviewStatus={editingTaskId ? reviews.get(editingTaskId)?.promptReviewStatus ?? "pending_review" : "pending_review"}
        projectContext={{ description: project.description, useDescriptionForAiPrompt: project.useDescriptionForAiPrompt }}
        reviewNavigation={draftTask ? undefined : { index: editingTaskIndex, total: tasks.length, canPrevious: editingTaskIndex > 0, canNext: editingTaskIndex >= 0 && editingTaskIndex < tasks.length - 1, onPrevious: () => { if (editingTaskIndex > 0) void openExistingEditor(tasks[editingTaskIndex - 1].id); }, onNext: () => { if (editingTaskIndex >= 0 && editingTaskIndex < tasks.length - 1) void openExistingEditor(tasks[editingTaskIndex + 1].id); } }}
        onEnhancePrompt={onEnhancePrompt} onClose={closeEditor} onSave={saveTask}
      />

      <BatchPromptDialog aiLabel={applicationSettings?.promptAiLabel} open={batchPromptOpen} taskCount={promptRequestIds.length} eligibility={promptEligibility} loading={promptEligibilityLoading} onRetry={() => void loadPromptEligibility(promptRequestIds)} projectBackgroundAvailable={project.useDescriptionForAiPrompt && Boolean(project.description.trim())} busy={batchPromptBusy} error={batchPromptError} onClose={closePromptBatch} onConfirm={(options) => void submitBatchPromptEnhancement(options)} />
      <BatchVideoDialog open={batchVideoOpen} selectedCount={videoRequestIds.length} title={videoRequestMode === "single" ? "生成当前视频" : "批量生成视频"} error={videoError} eligibility={batchVideoEligibility} loading={batchVideoLoading} submitting={batchVideoSubmitting} onClose={closeVideoBatch} onConfirm={() => void submitVideoBatch()} />

      <ProjectConfigPanel open={projectConfigOpen} project={project} onClose={() => setProjectConfigOpen(false)} onSave={onSaveProjectConfiguration} />

      <Dialog open={Boolean(playing)} size="wide" icon="video" title={playing ? `播放结果 · ${playing.task.title}` : "播放结果"} onClose={() => setPlaying(null)}>{playing && <TaskResultPlayer result={playing.result} taskNumber={playing.task.number}
        playlist={tasks.flatMap(task => { const result = task.id === playing.task.id ? playing.result : taskResult(project.snapshot, task); return result?.videoUrl ? [{ result, taskId: task.id, taskNumber: task.number, title: task.title }] : []; })}
        onCurrentChange={entry => { const task = tasks.find(task => task.id === entry.taskId); if (task) setPlaying({ result: entry.result, task }); }}
        onClose={() => setPlaying(null)} />}</Dialog>
    </main>
  );
}
