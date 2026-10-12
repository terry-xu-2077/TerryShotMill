import { VideoVersionSelect } from "./VideoVersionSelect";
import { GenerationProgress, TaskProgressLight } from "./GenerationProgress";
import { TaskRiskSticker } from "./TaskRiskSticker";
import { TaskNewResults, useViewedResults } from "./TaskNewResults";
import { TaskPreview } from "./TaskPreview";
import "./TaskCollection.css";
import {
  Clapperboard,
  LoaderCircle,
  Square,
  Images,
  Home,
  Download,
  Film,
  Play,
  Pencil,
  Plus,
  Sparkles,
  SlidersHorizontal,
  Upload,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import { Button } from "../../ui/primitives";

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
import type { ApplicationSettings, ProjectGateway } from "../../gateways/projectGateway";
import type { DirectorProject } from "./projectTypes";
import type {
  PromptEnhancementRequest,
  PromptEnhancementResponse,
} from "../../services/promptEnhancement";
import { ContextMenu, Dialog, OverlayPortal, useOverlayZIndex } from "../../ui/overlay";
import { TaskEditorDialog } from "../task/TaskEditorDialog";
import { updateTaskComposerFields } from "../task/storyboardMutations";
import {
  BatchPromptDialog,
  BatchVideoDialog,
  type PromptBatchOptions,
} from "./BatchReviewControls";
import { ProjectConfigPanel } from "./ProjectConfigPanel";
import { DirectorWorkspace, type DirectorPlaybackState, type DirectorToolbarState } from "./DirectorWorkspace";
import { TimelineOverview } from "./TimelineOverview";
import { TimelinePlayer } from "./TimelinePlayer";
import { GenerationResultBrowser } from "./GenerationResultBrowser";
import { ThemeSwitch } from "../../ui/ThemeSwitch";
import { TaskResultPlayer } from "./TaskResultPlayer";
import { formatElapsed, taskTimeSummary, useLiveTaskTimings } from "./taskTiming";
import type { LifecycleGateway } from "../../gateways/lifecycleGateway";
import { TaskLifecycleDialog, type TaskLifecycleIntent } from "./TaskLifecycleDialog";




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

function TaskInfoPanel({ history, snapshot, task, review, onPlayResult, timing, actions, newKinds, warnings, statusNote, referenceWarning }: {
  statusNote?: string | null;
  referenceWarning?: boolean;
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
        <div className="task-info-notices"><TaskNewResults kinds={newKinds} /><TaskRiskSticker tooltipOnly={referenceWarning} key={task.id} warnings={warnings} /></div>
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
  lifecycleGateway,
  onLifecycleChanged,
  bridgeStatus,
  project,
  promptReviewItems,
  onStopVideoJob,
  onVideoVersionChanged,
  onBack,
  onLoadTaskEditor,
  onCreateTask,
  onUpdateTask,
  gateway,
  onRefreshProject,
  onUpdateEditorPreference,
  onSaveProjectConfiguration,
  onChooseLocalFiles,
  onEnhancePrompt,
  onBatchEnhancePrompts,
  onCheckPromptBatchEligibility,
  onCheckVideoBatchEligibility,
  onCreateVideoBatch,
  applicationSettings,
  onRefreshComfyUIWorkflows,
}: {
  lifecycleGateway?: LifecycleGateway;
  onLifecycleChanged?: () => Promise<void>;
  bridgeStatus?: ReactNode;
  project: DirectorProject;
  promptReviewItems: PromptReviewItem[];
  onVideoVersionChanged?: () => Promise<void>;
  onStopVideoJob?: (jobId: string) => Promise<void>;
  onBack: () => void;
  onLoadTaskEditor: (taskId: string) => Promise<GenerationTask>;
  onCreateTask: (task: GenerationTask) => Promise<string>;
  onUpdateTask: (task: GenerationTask) => Promise<void>;
  gateway: ProjectGateway;
  onRefreshProject: () => Promise<void>;
  onUpdateEditorPreference?: (taskId: string, preference: Partial<import("../../gateways/projectGateway").TaskEditorView["editorPreference"]>) => Promise<void>;
  onSaveProjectConfiguration: (settings: ProjectSettingsPatch) => Promise<void>;
  onChooseLocalFiles?: () => Promise<string[]>;
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
  const [overviewModes, setOverviewModes] = useState<Record<string, "list" | "card">>({});
  const viewMode = overviewModes[project.id] ?? (project.director?.overviewViewMode === "card" ? "card" : "list");
  const [workspaceModes, setWorkspaceModes] = useState<Record<string, "overview" | "timeline">>({});
  const [viewSaveError, setViewSaveError] = useState("");
  const savedTimelineId = typeof project.director?.selectedTimelineId === "string" ? project.director.selectedTimelineId : null;
  const [timelineIds, setTimelineIds] = useState<Record<string, string>>({});
  const timelineId = timelineIds[project.id] ?? (project.snapshot.scenes.some(scene => scene.id === savedTimelineId) ? savedTimelineId : project.snapshot.scenes[0]?.id) ?? null;
  const workspaceMode = workspaceModes[project.id] ?? (project.director?.workspaceView === "timeline" && timelineId ? "timeline" : "overview");
  const setWorkspaceMode = (next: "overview" | "timeline", selectedTimelineId = timelineId) => {
    if (next === workspaceMode && selectedTimelineId === timelineId) return;
    const previous = workspaceMode;
    setWorkspaceModes(current => ({ ...current, [project.id]: next }));
    if (selectedTimelineId) setTimelineIds(current => ({ ...current, [project.id]: selectedTimelineId }));
    setViewSaveError("");
    void gateway.getProjectSettings(project.id)
      .then(settings => gateway.updateProject(project.id, { director: { ...settings.director, workspaceView: next, selectedTimelineId } }))
      .then(onRefreshProject)
      .catch(reason => {
        setWorkspaceModes(current => ({ ...current, [project.id]: previous }));
        setViewSaveError(reason instanceof Error ? reason.message : "视图设置保存失败");
      });
  };
  const showOverview = (next: "list" | "card") => {
    const previousMode = viewMode;
    const previousWorkspace = workspaceMode;
    setOverviewModes(current => ({ ...current, [project.id]: next }));
    setWorkspaceModes(current => ({ ...current, [project.id]: "overview" }));
    setViewSaveError("");
    void gateway.getProjectSettings(project.id)
      .then(settings => gateway.updateProject(project.id, { director: {
        ...settings.director, workspaceView: "overview", overviewViewMode: next, selectedTimelineId: timelineId,
      } }))
      .then(onRefreshProject)
      .catch(reason => {
        setOverviewModes(current => ({ ...current, [project.id]: previousMode }));
        setWorkspaceModes(current => ({ ...current, [project.id]: previousWorkspace }));
        setViewSaveError(reason instanceof Error ? reason.message : "视图设置保存失败");
      });
  };
  const [directorDirty, setDirectorDirty] = useState(false);
  const [directorDuration, setDirectorDuration] = useState("00:00:00:00");
  const [directorPlayback, setDirectorPlayback] = useState<DirectorPlaybackState>({ frame: 0, playing: false, clipId: null, clipStart: 0, clipEnd: 0 });
  const [directorToolbar, setDirectorToolbar] = useState<DirectorToolbarState>({
    readOnly: false, canEnhanceAll: false,
  });
  const directorAction = (action: string) => window.dispatchEvent(new CustomEvent("shotmill:director-action", { detail: action }));
  useEffect(() => {
    if (workspaceMode !== "timeline") return;
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (event.code !== "Space" || event.repeat || event.ctrlKey || event.metaKey || event.altKey
        || target.closest("input, textarea, select, button, [contenteditable=true], [role=dialog]")) return;
      event.preventDefault();
      directorAction("play-toggle");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [workspaceMode]);
  const [pendingExit, setPendingExit] = useState<"overview" | "results" | "home" | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [batchSelectedTaskIds, setBatchSelectedTaskIds] = useState<Set<string>>(() => new Set());
  const [managingTasks, setManagingTasks] = useState(false);
  const [lifecycleIntent, setLifecycleIntent] = useState<TaskLifecycleIntent | null>(null);
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
  const currentTimeline = project.snapshot.scenes.find(scene => scene.id === timelineId);
  const timelineTasks = useMemo(() => timelineId ? listTasksInStoryOrder(project.snapshot, timelineId) : [], [project.snapshot, timelineId]);
  const timelineProject = useMemo(() => ({ ...project, snapshot: { ...project.snapshot, tasks: timelineTasks } }), [project, timelineTasks]);
  const timings = useLiveTaskTimings(project.taskTimings);
  const reviews = useMemo(() => new Map(promptReviewItems.map((item) => [item.taskId, item])), [promptReviewItems]);
  useEffect(() => {
    if (directorDirty || !pendingExit) return;
    if (pendingExit === "overview") showOverview("list");
    else if (pendingExit === "results") showOverview("card");
    else onBack();
    setPendingExit(null);
  }, [directorDirty, pendingExit]);
  const leaveDirector = (target: "overview" | "results" | "home") => {
    if (!directorDirty) { if (target === "overview") showOverview("list"); else if (target === "results") showOverview("card"); else onBack(); return; }
    setPendingExit(target);
    window.dispatchEvent(new Event("shotmill:director-save-request"));
  };
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

  const handleTaskSelection = (event: Pick<ReactMouseEvent<HTMLButtonElement>, "shiftKey" | "ctrlKey" | "metaKey">, taskId: string, index: number) => {
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
          {lifecycleGateway && <Button disabled={!actionIds.length} onClick={() => setLifecycleIntent({ tasks: tasks.filter(task => actionIds.includes(task.id)) })}>删除</Button>}
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
          <Button onClick={() => workspaceMode === "timeline" ? leaveDirector("home") : onBack()} aria-label="返回项目首页"><Home size={16} /><span className="workspace-home-label">返回首页</span></Button>
          <Button onClick={() => setProjectConfigOpen(true)}><SlidersHorizontal size={16} strokeWidth={1.6} />项目配置</Button>
        </div>
        <div className="workspace-project-title"><strong>{project.title}</strong></div>
        <div className="workspace-top-actions">
          {workspaceMode === "timeline" && <div className="director-top-actions">
            <Button onClick={() => directorAction("import")}><Upload size={15} />导入</Button>
            <Button onClick={() => directorAction("export")}><Download size={15} />导出</Button>
          </div>}
          {bridgeStatus}
          <ThemeSwitch />
        </div>
      </header>

      <div className={`project-workspace-body${workspaceMode === "timeline" ? " is-director" : " is-overview"}`}>
        <aside className="workspace-sidebar" aria-label="工作区导航">
          <span className="workspace-sidebar-label">项目工作区</span>
          <button type="button" className={`workspace-sidebar-item${workspaceMode === "overview" && viewMode === "list" ? " is-active" : ""}`} aria-current={workspaceMode === "overview" && viewMode === "list" ? "page" : undefined} onClick={() => { if (workspaceMode === "timeline") leaveDirector("overview"); else if (viewMode !== "list") showOverview("list"); }}><Film size={18} />时间线列表</button>
          {currentTimeline && <button type="button" className={`workspace-sidebar-item is-sub${workspaceMode === "timeline" ? " is-active" : ""}`} aria-current={workspaceMode === "timeline" ? "page" : undefined} onClick={() => { if (workspaceMode !== "timeline") setWorkspaceMode("timeline", timelineId); }}><Clapperboard size={18} /><span>{currentTimeline.title}</span></button>}
          <button type="button" className={`workspace-sidebar-item${workspaceMode === "overview" && viewMode === "card" ? " is-active" : ""}`} aria-current={workspaceMode === "overview" && viewMode === "card" ? "page" : undefined} onClick={() => { if (workspaceMode === "timeline") leaveDirector("results"); else if (viewMode !== "card") showOverview("card"); }}><Images size={18} />生成结果</button>
        </aside>
        <div className="project-task-column">
        {workspaceMode === "timeline" && <TimelinePlayer tasks={timelineTasks} results={project.snapshot.results} playback={directorPlayback} onToggle={() => directorAction("play-toggle")} />}
        <section className={`project-task-area${workspaceMode === "timeline" ? " is-director" : ""}`} aria-label="任务区域">
          <header className={`task-collection-heading${workspaceMode === "timeline" ? " is-director" : ""}`}>
            {workspaceMode === "timeline" ? <div className="director-heading-leading">
              <h2>{currentTimeline?.title ?? "导演时间线"}</h2>
              <Button disabled={directorToolbar.readOnly} onClick={() => directorAction("new")}><Plus size={15} />新建片段</Button>
            </div> : <h2>{viewMode === "list" ? "时间线" : "生成结果"}</h2>}
            {workspaceMode === "timeline" && <span className="director-duration">总时长 <strong>{directorDuration}</strong></span>}
            {workspaceMode === "timeline" && <div className="director-heading-actions">
              <Button disabled={directorToolbar.readOnly} onClick={() => directorAction("global-prompt")}><Pencil size={15} />全局提示词</Button>
              <Button disabled={!directorToolbar.canEnhanceAll} onClick={() => directorAction("enhance-all")}><Sparkles size={15} />一键增强所有提示词</Button>
            </div>}
            {viewSaveError && <span className="workspace-view-save-error" role="alert">{viewSaveError}</span>}
          </header>
          {workspaceMode === "timeline" && timelineId && currentTimeline ? <DirectorWorkspace key={timelineId} project={timelineProject} timelineId={timelineId} gateway={gateway} lifecycleGateway={lifecycleGateway} onChooseLocalFiles={onChooseLocalFiles} onRefresh={onRefreshProject} selectedId={selectedTaskId} onSelection={setSelectedTaskId} onDirtyChange={setDirectorDirty} onDuration={setDirectorDuration} onPlayback={setDirectorPlayback} onToolbarChange={setDirectorToolbar} onClose={() => leaveDirector("overview")} onGenerate={async ids => { const eligible = await onCheckVideoBatchEligibility(ids); if (eligible.eligibleTaskIds.length !== ids.length) throw new Error("部分片段暂时不能生成，请检查任务状态"); await onCreateVideoBatch(ids); }} /> : viewMode === "list" ? (
            <TimelineOverview project={project} gateway={gateway} onRefresh={onRefreshProject} onOpen={id => setWorkspaceMode("timeline", id)} />
          ) : (
            <GenerationResultBrowser project={project} onPlay={(result, task) => setPlaying({ result, task })} />
          )}
        </section>
        </div>

      </div>


      {stopError && <Dialog open icon="warning" title="停止任务失败" onClose={() => setStopError("")}><p>{stopError}</p><Button onClick={() => setStopError("")}>知道了</Button></Dialog>}
      {lifecycleIntent && lifecycleGateway && onLifecycleChanged && <TaskLifecycleDialog
        projectId={project.id} intent={lifecycleIntent} gateway={lifecycleGateway}
        onClose={() => setLifecycleIntent(null)} onChanged={onLifecycleChanged} />}
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
        playlist={project.snapshot.results.flatMap(result => { const job = project.snapshot.jobs.find(item => item.id === result.jobId); const task = tasks.find(item => item.id === job?.taskId); return task && result.videoUrl ? [{ result, taskId: task.id, taskNumber: task.number, title: task.title }] : []; })}
        onCurrentChange={entry => { const task = tasks.find(task => task.id === entry.taskId); if (task) setPlaying({ result: entry.result, task }); }}
        onClose={() => setPlaying(null)} />}</Dialog>
    </main>
  );
}
