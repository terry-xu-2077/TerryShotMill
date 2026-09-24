import { RangeSlider } from "../../ui/RangeSlider";
import { Slider } from "../../ui/Slider";
import { ChevronDown, ChevronLeft, ChevronRight, Code2, Eye, Pencil, SlidersHorizontal, Sparkles } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Button, Checkbox, SegmentedControl } from "../../ui/primitives";
import { Select } from "../../ui/Select";

import { H3PromptEditor, type H3PromptViewMode } from "../prompt/H3PromptEditor";
import type { PromptAsset } from "../prompt/PromptAssetEditor";
import type { GenerationTask, ProjectAsset } from "../../domain/storyboard";
import type { PromptReviewStatus } from "../../gateways/batchReviewGateway";
import type { ComfyUIWorkflow, ComfyUIWorkflowProfile, WorkflowInputSelection } from "../../gateways/projectGateway";
import { WorkflowInputSlots } from "./WorkflowInputSlots";
import { workflowDurationDescription } from "./workflowDuration";
import type {
  PromptEnhancementRequest,
  PromptEnhancementResponse,
} from "../../services/promptEnhancement";
import { Dialog, Popover } from "../../ui/overlay";

type TaskEditorPatch = Partial<Pick<GenerationTask,
  "title" | "aiPrompt" | "finalPrompt" | "generationParams" | "plannedDurationSeconds" | "assetBindings"
>>;

type TaskEditorSave = { bivarianceHack(patch: TaskEditorPatch): void | Promise<void> }["bivarianceHack"];

type ReviewNavigation = {
  index: number;
  total: number;
  canPrevious: boolean;
  canNext: boolean;
  onPrevious: () => void;
  onNext: () => void;
};

type TaskEditorDialogProps = {
  open: boolean;
  task?: GenerationTask;
  assets: ProjectAsset[];
  workflowProfiles?: ComfyUIWorkflowProfile[];
  defaultWorkflowProfileId?: string;
  onLoadWorkflows?: () => Promise<ComfyUIWorkflow[]>;
  previousTaskDurationSeconds?: number;
  previousTaskId?: string;
  previousTaskSummary?: string;
  isNewTask?: boolean;
  readOnly?: boolean;
  reviewNavigation?: ReviewNavigation;
  reviewStatus?: PromptReviewStatus;
  projectContext?: { description: string; useDescriptionForAiPrompt: boolean };
  onEnhancePrompt?: (request: PromptEnhancementRequest) => Promise<PromptEnhancementResponse>;
  onUpdateEditorPreference?: (taskId: string, preference: Partial<import("../../gateways/projectGateway").TaskEditorView["editorPreference"]>) => Promise<void>;
  onClose: () => void;
  onViewPromptRevision?: (id: string) => void;
  onSave: TaskEditorSave;
};

type PromptMode = "user" | "ai";
type ContextMode = "片段承接" | "尾帧承接" | "不承接";
type AiPromptHistoryItem = {
  id: string;
  createdAt: string;
  prompt: string;
  sourceUserPrompt: string;
  previousTaskSummary?: string;
  projectBackgroundUsed?: boolean;
};

function assetKind(asset: ProjectAsset, role?: string): PromptAsset["kind"] {
  if (role === "character") return "subject";
  if (asset.mediaType === "video") return "video";
  if (asset.mediaType === "audio") return "audio";
  return "picture";
}

function promptAssetsForTask(task: GenerationTask | undefined, assets: ProjectAsset[], aiHistory: AiPromptHistoryItem[]): PromptAsset[] {
  if (!task) return [];
  const assetsById = new Map(assets.map((asset) => [asset.id, asset]));
  const reservedReferences = new Set(task.assetBindings.flatMap((binding) => binding.reference ? [binding.reference] : []));
  // Logical H3 subjects are not project assets. Never allocate their identifiers
  // to unrelated library items just because those items are available in @.
  const existingPrompts = [task.finalPrompt, task.aiPrompt ?? "", task.userIntent, ...aiHistory.map((item) => item.prompt)].join("\n");
  for (const match of existingPrompts.matchAll(/<(Subject|Picture|Video|Audio)\s+(\d+)>/gi)) {
    const kind = match[1][0].toUpperCase() + match[1].slice(1).toLowerCase();
    reservedReferences.add(`<${kind} ${Number(match[2])}>`);
  }
  const counters: Record<PromptAsset["kind"], number> = { subject: 0, picture: 0, video: 0, audio: 0 };
  return task.assetBindings.filter((binding) => assetsById.has(binding.assetId)).map((binding) => {
    const asset = assetsById.get(binding.assetId)!;
    const role = binding?.role ?? (asset.mediaType === "audio" ? "audio" : asset.category);
    const kind = assetKind(asset, role);
    const referenceType = kind === "subject" ? "Subject" : kind[0].toUpperCase() + kind.slice(1);
    let reference = binding?.reference;
    if (!reference) {
      do { reference = `<${referenceType} ${++counters[kind]}>`; } while (reservedReferences.has(reference));
      reservedReferences.add(reference);
    }
    return {
      id: asset.id,
      name: asset.name,
      kind,
      reference,
      detail: role === "character" ? "角色素材" : role === "scene" ? "场景素材" : role === "prop" ? "道具素材" : role === "audio" ? "音频素材" : "参考素材",
      tone: kind === "subject" ? "amber" : kind === "video" ? "green" : kind === "audio" ? "violet" : "blue",
      previewUrl: asset.previewUrl,
    };
  });
}

function stringParam(params: Record<string, unknown>, key: string, fallback: string) {
  const value = params[key];
  return typeof value === "string" && value ? value : fallback;
}
function numberParam(params: Record<string, unknown>, key: string, fallback: number) {
  const value = params[key];
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}
function normalizeContextMode(value: string): ContextMode {
  if (value === "自动承接" || value === "片段承接") return "片段承接";
  if (value === "尾帧承接") return "尾帧承接";
  return "不承接";
}
function normalizePromptMode(params: Record<string, unknown>, task: GenerationTask): PromptMode {
  if (params.promptSource === "ai" || params.promptSource === "user") return params.promptSource;
  if (task.aiPrompt?.trim() && task.finalPrompt === task.aiPrompt) return "ai";
  return "user";
}
function normalizeViewMode(params: Record<string, unknown>, key: string): H3PromptViewMode {
  return params[key] === "text" ? "text" : "visual";
}
function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}
function readAiHistory(params: Record<string, unknown>, task: GenerationTask): AiPromptHistoryItem[] {
  const raw = params.aiPromptHistory;
  if (Array.isArray(raw)) {
    const parsed = raw.flatMap((item): AiPromptHistoryItem[] => {
      if (!item || typeof item !== "object") return [];
      const value = item as Record<string, unknown>;
      if (typeof value.id !== "string" || typeof value.prompt !== "string") return [];
      return [{
        id: value.id,
        createdAt: typeof value.createdAt === "string" ? value.createdAt : "",
        prompt: value.prompt,
        sourceUserPrompt: typeof value.sourceUserPrompt === "string" ? value.sourceUserPrompt : "",
        previousTaskSummary: typeof value.previousTaskSummary === "string" ? value.previousTaskSummary : undefined,
        projectBackgroundUsed: value.projectBackgroundUsed === true,
      }];
    });
    if (parsed.length) return parsed;
  }
  return task.aiPrompt?.trim() ? [{
    id: `legacy-${task.id}`,
    createdAt: "",
    prompt: task.aiPrompt,
    sourceUserPrompt: stringParam(params, "userPrompt", task.userIntent || task.summary || ""),
  }] : [];
}
function formatHistoryLabel(item: AiPromptHistoryItem, index: number, total: number) {
  if (item.id.startsWith("saved-")) return "已保存的修改";
  if (!item.createdAt) return total === 1 ? "已有 AI 提示词" : `增强记录 ${index + 1}`;
  const date = new Date(item.createdAt);
  const time = Number.isNaN(date.getTime()) ? "" : new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(date);
  return `${index === total - 1 ? "最新版本" : `增强记录 ${index + 1}`}${time ? ` · ${time}` : ""}`;
}

const formatSeconds = (value: number) => `${Number(value.toFixed(2))}s`;

function ContinuationRange({ maxSeconds, start, end, onChange, readOnly = false }: { maxSeconds: number; start: number; end: number; onChange: (start: number, end: number) => void; readOnly?: boolean }) {
  const max = Math.max(0, maxSeconds);
  if (max === 0) return <div className="simple-context-range-empty">当前任务前没有可承接的片段。</div>;
  const duration = Number((end - start).toFixed(10));
  if (readOnly) return <p className="simple-context-note">{formatSeconds(start)} – {formatSeconds(end)} · {formatSeconds(duration)}</p>;
  return (
    <Popover label="承接时间轴" triggerLabel="调整承接区间" className="context-timeline-popover" triggerClassName="context-timeline-trigger"
      trigger={<><span>{formatSeconds(start)} – {formatSeconds(end)} · {formatSeconds(duration)}</span><SlidersHorizontal size={15} /></>}>
      {close => <div className="context-timeline-editor">
      <header>承接区间 · 来源 {formatSeconds(max)}</header>
      <div className="simple-context-range-control">
      <RangeSlider variant="timeline" selectionLabel="承接片段" min={0} max={max} step={0.1} minDistance={Math.min(0.1, max)}
        value={[start, end]} startLabel="承接起点" endLabel="承接终点"
        formatValue={formatSeconds} onChange={([nextStart, nextEnd]) => onChange(nextStart, nextEnd)} />
      </div>
      <footer><span>拖动片段平移，拖动两端裁剪</span><Button onClick={close}>完成</Button></footer>
      </div>}
    </Popover>
  );
}

export function TaskEditorDialog({
  open, task: incomingTask, assets, previousTaskDurationSeconds = 0, previousTaskId, previousTaskSummary = "", isNewTask = false,
  reviewNavigation, projectContext, onEnhancePrompt, onUpdateEditorPreference, onClose, onSave, onViewPromptRevision,
  workflowProfiles = [], defaultWorkflowProfileId = "", onLoadWorkflows,
  readOnly: readOnlyOverride,
}: TaskEditorDialogProps) {
  // Keep the last task rendered while its dialog finishes the exit transition.
  const lastTask = useRef(incomingTask);
  if (incomingTask) lastTask.current = incomingTask;
  const task = incomingTask ?? lastTask.current;
  const readOnly = readOnlyOverride ?? (task?.state === "running" || task?.state === "queued");
  const [promptMode, setPromptMode] = useState<PromptMode>("user");
  const [parametersOpen, setParametersOpen] = useState(false);
  const parameterPanelId = useId();
  useEffect(() => { setParametersOpen(false); }, [open, task?.id]);
  const [userViewMode, setUserViewMode] = useState<H3PromptViewMode>("visual");
  const [aiViewMode, setAiViewMode] = useState<H3PromptViewMode>("visual");
  const [taskTitle, setTaskTitle] = useState("");
  const [editingTitle, setEditingTitle] = useState(false);
  const [userPrompt, setUserPrompt] = useState("");
  const [userHistory, setUserHistory] = useState<{ id: string; prompt: string; createdAt: string }[]>([]);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiHistory, setAiHistory] = useState<AiPromptHistoryItem[]>([]);
  const [selectedAiHistoryId, setSelectedAiHistoryId] = useState("");
  const [isEnhancing, setIsEnhancing] = useState(false);
  const [includePreviousSummary, setIncludePreviousSummary] = useState(false);
  useEffect(() => { setIncludePreviousSummary(false); }, [open, task?.id]);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [preferenceError, setPreferenceError] = useState(false);
  const preferenceRequest = useRef(0);
  const [enhanceError, setEnhanceError] = useState("");
  const [duration, setDuration] = useState(6);
  const [resolution, setResolution] = useState("1080p");
  const [quality, setQuality] = useState("标准");
  const [workflowProfileId, setWorkflowProfileId] = useState("");
  const [generationMode, setGenerationMode] = useState("全能参考");
  const [contextMode, setContextMode] = useState<ContextMode>("尾帧承接");
  const [contextStartSeconds, setContextStartSeconds] = useState(0);
  const [contextEndSeconds, setContextEndSeconds] = useState(0);
  const [taskRevision, setTaskRevision] = useState<number | undefined>();
  const [inputBindings, setInputBindings] = useState<GenerationTask["assetBindings"]>([]);
  const [workflowInputs, setWorkflowInputs] = useState<WorkflowInputSelection | null>(null);
  const initializedTask = useRef<GenerationTask | undefined>(undefined);
  useEffect(() => {
    if (open && promptMode === "ai" && selectedAiHistoryId && initializedTask.current === task) {
      onViewPromptRevision?.(selectedAiHistoryId);
    }
  }, [open, promptMode, selectedAiHistoryId, task, onViewPromptRevision]);
  const [initialDraftSignature, setInitialDraftSignature] = useState("");
  const [pendingNavigation, setPendingNavigation] = useState<"previous" | "next" | null>(null);

  useEffect(() => {
    if (!open || !task) return;
    const params = task.generationParams ?? {};
    setInputBindings(task.assetBindings);
    setWorkflowInputs((params.workflowInputs as WorkflowInputSelection | undefined) ?? null);
    const initialPromptMode = normalizePromptMode(params, task);
    const storedUserPrompt = stringParam(params, "userPrompt", "");
    const initialUserPrompt = storedUserPrompt || (initialPromptMode === "user" ? task.finalPrompt || task.userIntent || task.summary || "" : task.userIntent || task.summary || "");
    const history = readAiHistory(params, task);
    const selectedHistory = history.find((item) => item.id === stringParam(params, "selectedAiPromptHistoryId", "")) ?? history.at(-1);
    const previousDuration = Math.max(0, previousTaskDurationSeconds);
    const legacyContextDuration = Math.max(1, numberParam(params, "contextDurationSeconds", 1));
    const defaultEnd = previousDuration;
    const defaultStart = Math.max(0, defaultEnd - Math.min(legacyContextDuration, Math.max(1, previousDuration)));
    const minInterval = Math.min(0.1, previousDuration);
    const storedEnd = previousDuration > 0 ? clamp(numberParam(params, "contextEndSeconds", defaultEnd), minInterval, previousDuration) : 0;
    const storedStart = storedEnd > 0 ? clamp(numberParam(params, "contextStartSeconds", defaultStart), 0, storedEnd - minInterval) : 0;

    setPromptMode(initialPromptMode);
    if (initializedTask.current !== task) {
      setUserViewMode(normalizeViewMode(params, "userPromptViewMode"));
      setAiViewMode(normalizeViewMode(params, "aiPromptViewMode"));
      initializedTask.current = task;
    }
    setTaskTitle(task.title);
    setEditingTitle(false);
    setUserPrompt(initialUserPrompt);
    setUserHistory(Array.isArray(params.userPromptHistory) ? params.userPromptHistory as { id: string; prompt: string; createdAt: string }[] : []);
    setAiHistory(history);
    setSelectedAiHistoryId(selectedHistory?.id ?? "");
    setAiPrompt(selectedHistory?.prompt ?? task.aiPrompt ?? "");
    setIsEnhancing(false);
    setSaveError("");
    setPreferenceError(false);
    preferenceRequest.current += 1;
    setEnhanceError("");
    setDuration(task.plannedDurationSeconds || 6);
    setResolution(stringParam(params, "resolution", "1080p"));
    setQuality(stringParam(params, "quality", "标准"));
    setWorkflowProfileId(stringParam(params, "workflowProfileId", ""));
    setGenerationMode(stringParam(params, "generationMode", "全能参考"));
    setContextMode(normalizeContextMode(stringParam(params, "contextMode", "尾帧承接")));
    setContextStartSeconds(storedStart);
    setContextEndSeconds(storedEnd);
    setTaskRevision(typeof params.revision === "number" ? params.revision : undefined);
    setPendingNavigation(null);
    setInitialDraftSignature(JSON.stringify({
      taskTitle: task.title, userPrompt: initialUserPrompt,
      aiPrompt: selectedHistory?.prompt ?? task.aiPrompt ?? "", aiHistory: history,
      selectedAiHistoryId: selectedHistory?.id ?? "", promptMode: initialPromptMode,
      duration: task.plannedDurationSeconds || 6,
      resolution: stringParam(params, "resolution", "1080p"), quality: stringParam(params, "quality", "标准"),
      workflowProfileId: stringParam(params, "workflowProfileId", ""),
      generationMode: stringParam(params, "generationMode", "全能参考"),
      contextMode: normalizeContextMode(stringParam(params, "contextMode", "尾帧承接")),
      contextStartSeconds: storedStart, contextEndSeconds: storedEnd,
      inputBindings: task.assetBindings, workflowInputs: (params.workflowInputs as WorkflowInputSelection | undefined) ?? null,
    }));
  }, [open, previousTaskDurationSeconds, task, readOnly]);

  const promptAssets = useMemo(() => promptAssetsForTask(task ? { ...task, assetBindings: inputBindings } : undefined, assets, aiHistory), [assets, task, aiHistory, inputBindings]);
  if (!task) return null;
  const availableWorkflows = workflowProfiles.filter((profile) => profile.enabled && profile.workflowFile.trim());
  const defaultWorkflow = availableWorkflows.find((profile) => profile.id === defaultWorkflowProfileId)
    ?? availableWorkflows.find((profile) => profile.resolution === resolution && profile.quality === quality)
    ?? availableWorkflows[0];
  const selectedWorkflowId = workflowProfileId || defaultWorkflow?.id || "";
  const selectedWorkflow = availableWorkflows.find((profile) => profile.id === selectedWorkflowId);
  const workflowLabel = selectedWorkflow?.name || (selectedWorkflowId ? "工作流不可用" : "未配置工作流");
  const selectedResolution = resolution;
  const selectedQuality = selectedWorkflow?.quality || quality;
  const previousDuration = Math.max(0, previousTaskDurationSeconds);
  const contextDurationSeconds = previousDuration > 0 ? Number((contextEndSeconds - contextStartSeconds).toFixed(10)) : 0;
  const activePrompt = promptMode === "ai" ? aiPrompt : userPrompt;
  const activeViewMode = promptMode === "ai" ? aiViewMode : userViewMode;
  const persistViewModes = (userMode: H3PromptViewMode, aiMode: H3PromptViewMode) => {
    if (!task || isNewTask || !onUpdateEditorPreference) return;
    const requestId = ++preferenceRequest.current;
    setPreferenceError(false);
    void onUpdateEditorPreference(task.id, { userViewMode: userMode, aiViewMode: aiMode }).catch(() => {
      if (preferenceRequest.current === requestId) setPreferenceError(true);
    });
  };
  const setActiveViewMode = (mode: H3PromptViewMode) => {
    (promptMode === "ai" ? setAiViewMode : setUserViewMode)(mode);
    persistViewModes(promptMode === "user" ? mode : userViewMode, promptMode === "ai" ? mode : aiViewMode);
  };
  const projectBackground = projectContext?.useDescriptionForAiPrompt && projectContext.description.trim() ? projectContext.description.trim() : undefined;

  const updateAiPrompt = (value: string) => {
    setAiPrompt(value);
    if (selectedAiHistoryId) setAiHistory((current) => current.map((item) => item.id === selectedAiHistoryId ? { ...item, prompt: value } : item));
  };
  const selectAiHistory = (id: string) => {
    const item = aiHistory.find((entry) => entry.id === id);
    if (!item) return;
    setSelectedAiHistoryId(item.id);
    setAiPrompt(item.prompt);
    setEnhanceError("");
  };

  const enhancePrompt = async () => {
    if (readOnly) return;
    if (!userPrompt.trim()) return setEnhanceError("请先填写用户提示词。 ");
    if (!onEnhancePrompt) return setEnhanceError("AI 增强服务尚未接入。 ");
    setIsEnhancing(true);
    setEnhanceError("");
    try {
      const response = await onEnhancePrompt({
        taskId: task.id, isDraft: isNewTask, previousTaskId, userPrompt: userPrompt.trim(),
        previousTaskSummary: includePreviousSummary ? previousTaskSummary.trim() || undefined : undefined, projectBackground,
        assets: promptAssets.map((asset) => ({ id: asset.id, name: asset.name, reference: asset.reference, kind: asset.kind })),
        generation: { resolution: selectedResolution, quality: selectedQuality, mode: generationMode, durationSeconds: duration, contextMode, contextStartSeconds: contextMode === "片段承接" ? contextStartSeconds : undefined, contextEndSeconds: contextMode === "片段承接" ? contextEndSeconds : undefined },
      });
      if (!response.prompt.trim()) throw new Error("AI 增强没有返回提示词。 ");
      const item: AiPromptHistoryItem = { id: response.id || `ai-${Date.now()}`, createdAt: response.createdAt || new Date().toISOString(), prompt: response.prompt, sourceUserPrompt: userPrompt, previousTaskSummary: includePreviousSummary ? previousTaskSummary.trim() || undefined : undefined, projectBackgroundUsed: Boolean(projectBackground) };
      setAiHistory((current) => [...current, item]);
      setSelectedAiHistoryId(item.id);
      setAiPrompt(item.prompt);
      setPromptMode("ai");
      if (typeof response.taskRevision === "number") setTaskRevision(response.taskRevision);
    } catch (error) {
      setEnhanceError(error instanceof Error ? error.message : "AI 增强失败，请稍后重试。 ");
    } finally { setIsEnhancing(false); }
  };

  const buildPatch = (saveUserPromptVersion = false): TaskEditorPatch => {
    return {
      title: taskTitle.trim() || task.title,
      finalPrompt: activePrompt,
      aiPrompt,
      plannedDurationSeconds: duration,
      assetBindings: inputBindings,
      generationParams: {
        ...task.generationParams, workflowProfileId: selectedWorkflowId || undefined, workflowInputs, resolution: selectedResolution, quality: selectedQuality, generationMode, contextMode, contextDurationSeconds, contextStartSeconds, contextEndSeconds,
        saveUserPromptVersion, promptSource: promptMode, userPrompt, userPromptViewMode: userViewMode, aiPromptViewMode: aiViewMode,
        aiPromptHistory: aiHistory, selectedAiPromptHistoryId: selectedAiHistoryId || undefined, revision: taskRevision,
      },
    };
  };
  const save = async (saveUserPromptVersion = false) => {
    if (readOnly || isSaving || isEnhancing || (promptMode === "ai" && !aiPrompt.trim())) return;
    setIsSaving(true);
    setSaveError("");
    try {
      await onSave(buildPatch(saveUserPromptVersion));
      onClose();
    } catch {
      setSaveError("保存失败，编辑内容已保留。请检查服务连接后重试。");
    } finally { setIsSaving(false); }
  };
  const draftSignature = JSON.stringify({
    taskTitle, userPrompt, aiPrompt, aiHistory, selectedAiHistoryId, promptMode,
    duration, resolution, quality, workflowProfileId, generationMode, contextMode,
    contextStartSeconds, contextEndSeconds, inputBindings, workflowInputs,
  });
  const editorBusy = isSaving || isEnhancing;
  const navigate = (direction: "previous" | "next") => {
    if (!reviewNavigation || editorBusy) return;
    if (direction === "previous" ? !reviewNavigation.canPrevious : !reviewNavigation.canNext) return;
    if (!readOnly && draftSignature !== initialDraftSignature) {
      setSaveError("");
      setPendingNavigation(direction);
      return;
    }
    (direction === "previous" ? reviewNavigation.onPrevious : reviewNavigation.onNext)();
  };
  const continueNavigation = async (saveChanges: boolean) => {
    if (!pendingNavigation || !reviewNavigation || editorBusy) return;
    const action = pendingNavigation === "previous" ? reviewNavigation.onPrevious : reviewNavigation.onNext;
    setIsSaving(true);
    setSaveError("");
    try {
      if (saveChanges) await onSave(buildPatch());
      setPendingNavigation(null);
      action();
    } catch { setSaveError("保存失败，编辑内容已保留。请重试或继续编辑。"); }
    finally { setIsSaving(false); }
  };

  const titleNode = (
    <span className="task-dialog-title-shell">
      <span className="task-dialog-title">
        {readOnly ? <span>{taskTitle || task.title}</span> : editingTitle ? (
          <input autoFocus value={taskTitle} aria-label="任务名称" onChange={(event) => setTaskTitle(event.target.value)} onBlur={() => setEditingTitle(false)} onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); if (event.key === "Escape") { setTaskTitle(task.title); setEditingTitle(false); } }} />
        ) : (
          <button type="button" className="task-dialog-title-edit" title="编辑任务名称" onClick={() => setEditingTitle(true)}><span>{taskTitle || task.title}</span><Pencil size={14} aria-hidden="true" /></button>
        )}
      </span>
      {reviewNavigation && reviewNavigation.index >= 0 && (
        <span className="task-review-navigation" aria-label="任务审核导航">
          <button type="button" aria-label="上一个任务" disabled={editorBusy || !reviewNavigation.canPrevious} onClick={() => navigate("previous")}><ChevronLeft size={15} /></button>
          <span>{reviewNavigation.index + 1} / {reviewNavigation.total}</span>
          <button type="button" aria-label="下一个任务" disabled={editorBusy || !reviewNavigation.canNext} onClick={() => navigate("next")}><ChevronRight size={15} /></button>
        </span>
      )}
    </span>
  );

  return (
    <><Dialog open={open} size="wide" icon="task" title={titleNode} description={`任务编号 ${task.number}`} onClose={onClose} onKeyDown={(event) => {
      if (event.defaultPrevented || event.repeat || event.nativeEvent.isComposing || pendingNavigation || editorBusy) return;
      if (event.target instanceof Element && event.target.closest('[role="dialog"]') !== event.currentTarget) return;
      if (event.altKey && !event.ctrlKey && !event.metaKey && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
        event.preventDefault();
        navigate(event.key === "ArrowLeft" ? "previous" : "next");
      } else if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        if (!readOnly) void save();
      }
    }}>
      <div className="simple-task-editor" data-testid="simple-task-editor">
        <section className="task-parameter-disclosure">
          <button type="button" className="task-parameter-toggle" aria-label="生成参数" aria-expanded={parametersOpen} aria-controls={parameterPanelId} onClick={() => setParametersOpen((value) => !value)}>
            <SlidersHorizontal size={15} /> 生成参数 <ChevronDown className="task-parameter-chevron" size={14} />
            <span className="task-parameter-summary">{workflowLabel} · {duration} 秒 · {contextMode}</span>
          </button>
        <div className={`task-parameter-content ${parametersOpen ? "is-open" : ""}`} aria-hidden={!parametersOpen} inert={!parametersOpen}>
        <div className="task-parameter-clip">
        <aside id={parameterPanelId} className="simple-task-config" aria-label="任务配置">
          <section>
            <div className="simple-generation-heading"><h3>生成参数</h3><span>分辨率</span><span>总秒数</span></div>
            <div className="simple-generation-row">
            <div className="simple-workflow-field">
              <Select ariaLabel="生成工作流" value={selectedWorkflowId} onChange={(id) => { setWorkflowProfileId(id); setInputBindings([]); setWorkflowInputs(null); }} disabled={readOnly || availableWorkflows.length === 0} options={[
                ...(!selectedWorkflow ? [{ value: selectedWorkflowId, label: workflowLabel }] : []),
                ...availableWorkflows.map((profile) => ({ value: profile.id, label: profile.name })),
              ]} />
            </div>
            <div className="simple-workflow-field"><Select ariaLabel="生成分辨率" value={resolution} onChange={setResolution} disabled={readOnly} options={[{ value: "480p", label: "480p" }, { value: "720p", label: "720p" }, { value: "1080p", label: "1080p" }]} /></div>
            <div className="simple-slider-field"><Slider disabled={readOnly} min={1} max={15} allowOutOfRangeInput step={1} value={duration} ariaLabel="总秒数" onChange={setDuration} /></div>
              </div>
              <p className="workflow-duration-note">{workflowDurationDescription(selectedWorkflow, duration)}</p>
          </section>
          <section><h3>生成模式</h3><div className="task-parameter-control"><SegmentedControl disabled={readOnly} ariaLabel="生成模式" presentation="tabs" fluid value={generationMode} onChange={setGenerationMode} options={[{ value: "全能参考", label: "全能参考" }, { value: "首尾帧", label: "首尾帧" }]} /></div><div /></section>
          <section className="simple-context-section">
            <h3>上下文承接</h3>
            <div className="task-parameter-control"><SegmentedControl<ContextMode> disabled={readOnly} value={contextMode} onChange={setContextMode} ariaLabel="上下文承接方式" presentation="tabs" fluid options={[{ value: "片段承接", label: "片段承接" }, { value: "尾帧承接", label: "尾帧承接" }, { value: "不承接", label: "不承接" }]} /></div>
            <div className="simple-context-detail-slot">
              {contextMode === "片段承接" && <ContinuationRange readOnly={readOnly} maxSeconds={previousDuration} start={contextStartSeconds} end={contextEndSeconds} onChange={(start, end) => { setContextStartSeconds(start); setContextEndSeconds(end); }} />}
              {contextMode === "尾帧承接" && <p className="simple-context-note">使用上一任务最终帧作为本任务的起始视觉参考。</p>}
              {contextMode === "不承接" && <p className="simple-context-note">本任务独立生成，不引用上一任务的连续性信息。</p>}
            </div>
          </section>
        </aside>
        </div>
        </div>
        </section>

        <section className="simple-prompt-editor" aria-label={readOnly ? "提示词查看" : "提示词编辑"}>
          <header className="simple-prompt-head">
            <div className="simple-prompt-title-group"><h2>{readOnly ? "提示词查看" : "提示词编辑"}</h2><SegmentedControl<H3PromptViewMode> value={activeViewMode} onChange={setActiveViewMode} ariaLabel={`${promptMode === "ai" ? "AI增强" : "用户"}提示词显示模式`} presentation="tabs" compact className="simple-prompt-view-tabs" options={[{ value: "visual", label: "可视化", icon: <Eye size={13} /> }, { value: "text", label: "文本", icon: <Code2 size={13} /> }]} /></div>
            {promptMode === "user" && <div className="simple-ai-history-select"><Select ariaLabel="用户提示词历史版本" value={[...userHistory].reverse().find(item => item.prompt === userPrompt)?.id ?? ""} disabled={readOnly || !userHistory.length} onChange={id => { const item = userHistory.find(entry => entry.id === id); if (item) setUserPrompt(item.prompt); }} options={[{ value: "", label: userHistory.length ? "当前编辑内容" : "暂无保存记录" }, ...userHistory.map((item, index) => ({ value: item.id, label: `版本 ${index + 1} · ${new Date(item.createdAt).toLocaleString()}` }))]} /></div>}
            {promptMode === "user" && <Button disabled={readOnly || isSaving || isEnhancing || !userPrompt.trim()} title="保存任务并将当前用户提示词存为历史版本" onClick={() => void save(true)}>保存版本</Button>}
            {promptMode === "ai" && <div className="simple-ai-history-select"><Select value={selectedAiHistoryId} disabled={readOnly || !aiHistory.length} onChange={selectAiHistory} options={aiHistory.length ? aiHistory.map((item, index) => ({ value: item.id, label: formatHistoryLabel(item, index, aiHistory.length) })) : [{ value: "", label: "暂无增强记录" }]} /></div>}
            <SegmentedControl<PromptMode> value={promptMode} onChange={setPromptMode} ariaLabel="提示词版本" presentation="tabs" compact className="simple-prompt-tabs" options={[{ value: "user", label: "用户" }, { value: "ai", label: "AI 增强", icon: <Sparkles size={13} /> }]} />
          </header>

          <div className={`simple-prompt-body ${promptMode === "ai" ? "is-ai" : ""}`}>
            {promptMode === "user" ? <H3PromptEditor readOnly={readOnly} value={userPrompt} onChange={setUserPrompt} assets={promptAssets} ariaLabel="用户提示词" viewMode={userViewMode} /> : <>
              <H3PromptEditor readOnly={readOnly} value={aiPrompt} onChange={updateAiPrompt} assets={promptAssets} ariaLabel="AI 增强提示词" viewMode={aiViewMode} />
              {!aiPrompt.trim() && <div className="simple-ai-prompt-empty" aria-hidden="true"><span>{readOnly ? "暂无增强提示词" : "点击右下角“增强”，基于用户提示词生成一个新的增强版本。"}</span></div>}
              {enhanceError && <div className="simple-ai-enhance-error" role="alert">{enhanceError}</div>}
              {!readOnly && <div className="simple-ai-prompt-actions"><label className="single-prompt-context-option"><Checkbox ariaLabel="增强时参考上一任务摘要" checked={includePreviousSummary} disabled={isEnhancing || !previousTaskSummary.trim()} onChange={setIncludePreviousSummary} /><span>参考上一任务摘要</span></label><Button className="simple-ai-enhance-button" disabled={isEnhancing || !userPrompt.trim()} onClick={enhancePrompt}><Sparkles size={14} /> {isEnhancing ? "增强中…" : "增强"}</Button></div>}
            </>}
          </div>
          <WorkflowInputSlots readOnly={readOnly} open={open} workflowFile={selectedWorkflow?.workflowFile} loadWorkflows={onLoadWorkflows} assets={assets} bindings={inputBindings} value={workflowInputs} onChange={(value, bindings) => { setWorkflowInputs(value); setInputBindings(bindings); }} />
        </section>

        <footer className="simple-task-editor-actions">
          <div className="simple-task-prompt-source">
            {saveError && <span role="alert">{saveError}</span>}
            {preferenceError && <span role="alert">显示偏好未记住 <Button onClick={() => persistViewModes(userViewMode, aiViewMode)}>重试</Button></span>}
            <span role="status">{readOnly ? "排队或生成中 · 只读" : draftSignature !== initialDraftSignature ? "任务已修改 · 未保存" : isNewTask ? "新任务 · 未保存" : "任务已保存"}</span>
          </div>
          <div className="simple-task-editor-action-buttons">
            <Button onClick={onClose}>{readOnly ? "关闭" : "取消"}</Button>
            {!readOnly && <Button variant="accent" disabled={isSaving || isEnhancing || (promptMode === "ai" && !aiPrompt.trim())} onClick={() => void save()}>{isSaving ? "保存中…" : "保存"}</Button>}
          </div>
        </footer>
      </div>
    </Dialog>
    <Dialog open={open && pendingNavigation !== null} icon="save" title="未保存的修改" onClose={() => { if (!isSaving) setPendingNavigation(null); }}>
      <div className="task-navigation-confirm">
        <p>保存后切换任务？</p>
        {saveError && <p role="alert">{saveError}</p>}
        <div className="task-navigation-actions">
          <Button disabled={isSaving} onClick={() => setPendingNavigation(null)}>继续编辑</Button>
          <Button disabled={isSaving} onClick={() => void continueNavigation(false)}>放弃并切换</Button>
          <Button variant="accent" disabled={isSaving} onClick={() => void continueNavigation(true)}>{isSaving ? "保存中…" : "保存并切换"}</Button>
        </div>
      </div>
    </Dialog></>
  );
}
