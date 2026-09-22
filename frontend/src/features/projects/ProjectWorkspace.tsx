import { BrandLogo } from "../../components/BrandLogo";
import { TaskNewResults, useViewedResults } from "./TaskNewResults";
import { TaskRiskSticker } from "./TaskRiskSticker";
import {
  Check,
  FileImage,
  Film,
  Folder,
  Grid2X2,
  Home,
  List,
  Music2,
  Pencil,
  Play,
  Plus,
  Settings,
  SlidersHorizontal,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "terry-react-ui-library";

import {
  listTasksInStoryOrder,
  type GenerationTask,
  type ProjectAsset,
  type Result,
  type StoryboardDomainSnapshot,
} from "../../domain/storyboard";
import type { DirectorProject } from "../../mock/projects";
import type { ProjectSummary } from "../../gateways/projectGateway";
import { ContextMenu, Dialog } from "../../ui/overlay";
import { ThemeSwitch } from "../../ui/ThemeSwitch";
import { TaskEditorDialog } from "../storyboard/TaskEditorDialog";
import { insertTaskAfter, updateTaskComposerFields } from "../storyboard/storyboardMutations";

type TaskViewMode = "list" | "card";
type DisplayStatus = "idle" | "running" | "completed" | "failed";
type ProjectConfigTab = "info" | "assets";

type TaskEditorPatch = Partial<Pick<GenerationTask,
  "title" | "aiPrompt" | "finalPrompt" | "generationParams" | "plannedDurationSeconds"
>>;

type ProjectSettingsPatch = Pick<DirectorProject, "title" | "description" | "useDescriptionForAiPrompt">;

const taskStatusLabel: Record<DisplayStatus, string> = {
  idle: "未开始",
  running: "进行中",
  completed: "已完成",
  failed: "失败",
};

const assetCategoryLabel: Record<ProjectAsset["category"], string> = {
  character: "角色",
  scene: "场景",
  prop: "道具",
  reference: "参考",
};

function displayTaskStatus(task: GenerationTask): DisplayStatus {
  if (task.state === "completed") return "completed";
  if (task.state === "running" || task.state === "queued") return "running";
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
  const taskJobIds = new Set(snapshot.jobs.filter((job) => job.taskId === task.id).map((job) => job.id));
  return snapshot.results.slice().reverse().find((result) => taskJobIds.has(result.jobId));
}

function taskPreview(snapshot: StoryboardDomainSnapshot, task: GenerationTask) {
  return taskResult(snapshot, task)?.previewUrl ?? task.storyboardFrame.previewUrl;
}

function resultCount(snapshot: StoryboardDomainSnapshot, taskId: string) {
  const jobIds = new Set(snapshot.jobs.filter((job) => job.taskId === taskId).map((job) => job.id));
  return snapshot.results.filter((result) => jobIds.has(result.jobId)).length;
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
    summary: "等待填写提示词。",
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

export function ProjectHome({ bridgeStatus, projects, loading = false, error = "", onRetry, onOpenProject, onCreateProject }: {
  bridgeStatus?: import("react").ReactNode;
  projects: ProjectSummary[]; loading?: boolean; error?: string; onRetry?: () => void;
  onOpenProject: (projectId: string) => void; onCreateProject: () => void;
}) {
  const { unread } = useViewedResults();
  return <main className="project-home" aria-label="项目首页">
    <header className="project-home-title"><h1><BrandLogo />Terry导演工作台</h1>{bridgeStatus}<ThemeSwitch /></header>
    <div className="project-home-collection">
      <header className="project-collection-heading"><h2>项目</h2><span className="project-home-count">{projects.length} 个项目</span></header>
      <svg width="0" height="0" aria-hidden="true" style={{ position: "absolute" }}><defs>
        <clipPath id="project-folder-outline" clipPathUnits="objectBoundingBox"><path d="M0 .15 Q0 0 .06 0 H.32 C.36 0 .36 .13 .42 .13 H.94 Q1 .13 1 .27 V.87 Q1 1 .94 1 H.06 Q0 1 0 .87 Z" /></clipPath>
      </defs></svg>
      <section className="project-folder-grid" aria-label="项目列表">
        <button type="button" className="project-folder-card project-create-card" onClick={onCreateProject}><div><Plus className="creation-motion-icon" size={30} /><span>新建项目</span></div></button>
        {loading && projects.length === 0 && <div className="project-folder-card project-create-card" role="status">正在加载项目…</div>}
        {!loading && error && projects.length === 0 && <button type="button" className="project-folder-card project-create-card" onClick={onRetry}><div><span>项目加载失败，点击重试</span></div></button>}
        {projects.map(project => {
          const kinds = [...new Set((project.newResults ?? []).flatMap(unread))];
          return <div key={project.id} className="project-folder-item">
            <button type="button" className={`project-folder-card is-${project.status} ${project.coverUrl ? "has-cover" : "is-empty"}`} onClick={() => onOpenProject(project.id)} aria-label={`打开项目 ${project.title}`}>
              {project.coverUrl && <><div className="project-folder-sheet project-folder-paper" aria-hidden="true" /><div className="project-folder-sheet project-folder-paper-middle" aria-hidden="true" /></>}
              <div className="project-folder-sheet project-folder-cover" style={project.coverUrl ? { backgroundImage: `url("${project.coverUrl}")` } : undefined} />
              <div className="project-folder-front">
                <div className="project-folder-tab"><time className="project-folder-date" dateTime={project.createdAt}>{project.createdAt ? new Date(project.createdAt).toLocaleDateString("zh-CN") : ""}</time></div>
                <h2>{project.title}</h2><p className="project-folder-description">{project.description || "暂无项目简介"}</p>
                <footer><span>{project.taskCount} 个任务</span><span>{project.assetCount} 个资产</span><span>已生成 {project.completedTaskCount ?? 0}/{project.taskCount}</span></footer>
              </div>
            </button><div className="project-folder-notices"><TaskNewResults kinds={kinds} /><TaskRiskSticker warnings={project.generationWarnings ?? []} /></div>
          </div>;
        })}
      </section>
    </div>
  </main>;
}

function TaskPreview({ previewUrl, compact = false }: { previewUrl?: string; compact?: boolean }) {
  return (
    <div
      className={`task-preview ${compact ? "is-compact" : ""}`}
      style={previewUrl ? { backgroundImage: `url("${previewUrl}")` } : undefined}
    >
      {!previewUrl && <Play size={compact ? 22 : 44} />}
    </div>
  );
}

function TaskInfoPanel({
  snapshot,
  task,
  onPlayResult,
}: {
  snapshot: StoryboardDomainSnapshot;
  task?: GenerationTask;
  onPlayResult: (result: Result, task: GenerationTask) => void;
}) {
  if (!task) {
    return (
      <aside className="project-task-info" aria-label="任务信息">
        <div className="project-task-info-empty">选择一个任务查看信息</div>
      </aside>
    );
  }

  const params = task.generationParams ?? {};
  const status = displayTaskStatus(task);
  const prompt = promptSummary(task);
  const result = taskResult(snapshot, task);
  const preview = taskPreview(snapshot, task);

  return (
    <aside className="project-task-info" aria-label="任务信息">
      {result ? (
        <button type="button" className="task-result-preview-button" onClick={() => onPlayResult(result, task)} aria-label={`播放任务 ${task.title} 的生成结果`}>
          <TaskPreview previewUrl={preview} />
          <span className="task-result-play"><Play size={25} fill="currentColor" /></span>
        </button>
      ) : (
        <TaskPreview previewUrl={preview} />
      )}
      <h2>任务名：{task.title}</h2>

      <section className="project-info-block">
        <h3>提示词</h3>
        <p>{prompt}</p>
      </section>

      <section className="project-info-block">
        <h3>生成参数</h3>
        <dl>
          <div><dt>状态</dt><dd><span className={`workspace-status-dot is-${status}`} />{taskStatusLabel[status]}</dd></div>
          <div><dt>时长</dt><dd>{task.plannedDurationSeconds || 0} 秒</dd></div>
          <div><dt>分辨率</dt><dd>{String(params.resolution ?? "1080P").toUpperCase()}</dd></div>
          <div><dt>质量</dt><dd>{String(params.quality ?? "标准")}</dd></div>
        </dl>
      </section>
    </aside>
  );
}

function assetMediaIcon(asset: ProjectAsset) {
  if (asset.mediaType === "video") return <Film size={16} />;
  if (asset.mediaType === "audio") return <Music2 size={16} />;
  return <FileImage size={16} />;
}

function ProjectConfigDialog({
  open,
  project,
  onClose,
  onSave,
}: {
  open: boolean;
  project: DirectorProject;
  onClose: () => void;
  onSave: (settings: ProjectSettingsPatch, assets: ProjectAsset[]) => void;
}) {
  const [tab, setTab] = useState<ProjectConfigTab>("info");
  const [title, setTitle] = useState(project.title);
  const [description, setDescription] = useState(project.description);
  const [useDescriptionForAiPrompt, setUseDescriptionForAiPrompt] = useState(project.useDescriptionForAiPrompt);
  const [assets, setAssets] = useState<ProjectAsset[]>(project.snapshot.assets);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setTab("info");
    setTitle(project.title);
    setDescription(project.description);
    setUseDescriptionForAiPrompt(project.useDescriptionForAiPrompt);
    setAssets(project.snapshot.assets.map((asset) => ({ ...asset, tags: [...asset.tags] })));
  }, [open, project]);

  const importFiles = (files: FileList | null) => {
    if (!files?.length) return;
    const nextAssets = Array.from(files).map((file, index): ProjectAsset => {
      const mediaType: ProjectAsset["mediaType"] = file.type.startsWith("video/")
        ? "video"
        : file.type.startsWith("audio/")
          ? "audio"
          : "image";
      return {
        id: `asset-local-${Date.now()}-${index}`,
        name: file.name.replace(/\.[^.]+$/, "") || file.name,
        mediaType,
        category: "reference",
        projectRelativePath: file.name,
        previewUrl: mediaType === "audio" ? undefined : URL.createObjectURL(file),
        tags: [],
        checksum: `local-${file.size}-${file.lastModified}`,
      };
    });
    setAssets((current) => [...current, ...nextAssets]);
  };

  return (
    <Dialog open={open} size="wide" icon="configure" title="项目配置" description="管理项目级信息与资产。" onClose={onClose}>
      <div className="project-config-dialog">
        <nav className="project-config-tabs" aria-label="项目配置分类">
          <button type="button" className={tab === "info" ? "is-active" : ""} onClick={() => setTab("info")}>项目信息</button>
          <button type="button" className={tab === "assets" ? "is-active" : ""} onClick={() => setTab("assets")}>资产管理 <span>{assets.length}</span></button>
        </nav>

        <section className="project-config-content">
          {tab === "info" ? (
            <div className="project-config-info">
              <label>
                <span>项目标题</span>
                <input value={title} onChange={(event) => setTitle(event.target.value)} />
              </label>
              <label>
                <span>项目简介</span>
                <textarea
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  rows={8}
                  placeholder="用几句话说明项目的世界观、题材、角色关系或视觉基调。"
                />
              </label>
              <label className="project-context-checkbox">
                <input
                  type="checkbox"
                  checked={useDescriptionForAiPrompt}
                  onChange={(event) => setUseDescriptionForAiPrompt(event.target.checked)}
                />
                <span>
                  <strong>AI 增强时使用项目简介作为背景</strong>
                  <small>启用后，项目简介会作为项目级背景信息提供给提示词增强服务，不直接写入用户提示词。</small>
                </span>
              </label>
            </div>
          ) : (
            <div className="project-asset-manager">
              <header>
                <div><strong>项目资产</strong><span>{assets.length} 项</span></div>
                <Button onClick={() => inputRef.current?.click()}><Upload size={14} /> 添加资产</Button>
                <input
                  ref={inputRef}
                  hidden
                  type="file"
                  multiple
                  accept="image/*,video/*,audio/*"
                  onChange={(event) => {
                    importFiles(event.target.files);
                    event.currentTarget.value = "";
                  }}
                />
              </header>
              <div className="project-asset-list">
                {assets.map((asset) => (
                  <article key={asset.id} className="project-asset-row">
                    <div className="project-asset-thumb" style={asset.previewUrl ? { backgroundImage: `url("${asset.previewUrl}")` } : undefined}>
                      {!asset.previewUrl && assetMediaIcon(asset)}
                    </div>
                    <div className="project-asset-copy">
                      <strong>{asset.name}</strong>
                      <span>{assetCategoryLabel[asset.category]} · {asset.mediaType === "image" ? "图片" : asset.mediaType === "video" ? "视频" : "音频"}</span>
                    </div>
                    <button type="button" className="project-asset-remove" aria-label={`移除资产 ${asset.name}`} onClick={() => setAssets((current) => current.filter((item) => item.id !== asset.id))}><Trash2 size={15} /></button>
                  </article>
                ))}
                {!assets.length && <div className="project-asset-empty">项目还没有资产。添加后可在任务提示词中使用 @ 引用。</div>}
              </div>
            </div>
          )}
        </section>

        <footer className="project-config-actions">
          <Button onClick={onClose}>取消</Button>
          <Button variant="accent" disabled={!title.trim()} onClick={() => {
            onSave({
              title: title.trim(),
              description: description.trim(),
              useDescriptionForAiPrompt,
            }, assets);
            onClose();
          }}>保存</Button>
        </footer>
      </div>
    </Dialog>
  );
}

export function ProjectWorkspace({
  project,
  onBack,
  onRenameProject,
  onUpdateProjectSettings,
  onSnapshotChange,
}: {
  project: DirectorProject;
  onBack: () => void;
  onRenameProject: (title: string) => void;
  onUpdateProjectSettings: (settings: ProjectSettingsPatch) => void;
  onSnapshotChange: (snapshot: StoryboardDomainSnapshot) => void;
}) {
  const [viewMode, setViewMode] = useState<TaskViewMode>("list");
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [draftTask, setDraftTask] = useState<GenerationTask | null>(null);
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState(project.title);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [projectConfigOpen, setProjectConfigOpen] = useState(false);
  const [playing, setPlaying] = useState<{ result: Result; task: GenerationTask } | null>(null);

  const tasks = useMemo(() => orderedTasks(project.snapshot), [project.snapshot]);
  const selectedTask = tasks.find((task) => task.id === selectedTaskId);
  const editingTask = draftTask ?? tasks.find((task) => task.id === editingTaskId);
  const runningTask = tasks.find((task) => ["running", "queued"].includes(task.state));

  useEffect(() => {
    if (selectedTaskId && tasks.some((task) => task.id === selectedTaskId)) return;
    setSelectedTaskId(tasks[0]?.id ?? null);
  }, [selectedTaskId, tasks]);

  useEffect(() => setRenameValue(project.title), [project.title]);

  const openExistingEditor = (taskId: string) => {
    setSelectedTaskId(taskId);
    setDraftTask(null);
    setEditingTaskId(taskId);
  };

  const openNewTask = () => {
    const task = makeDraftTask(project.snapshot);
    setDraftTask(task);
    setEditingTaskId(null);
  };

  const closeEditor = () => {
    setDraftTask(null);
    setEditingTaskId(null);
  };

  const saveTask = (patch: TaskEditorPatch) => {
    if (draftTask) {
      const firstSceneId = project.snapshot.scenes.slice().sort((a, b) => a.orderKey.localeCompare(b.orderKey))[0]?.id;
      if (!firstSceneId) return;
      const finalPrompt = patch.finalPrompt ?? draftTask.finalPrompt;
      const savedTask: GenerationTask = {
        ...draftTask,
        ...patch,
        summary: finalPrompt.trim() || draftTask.summary,
        generationParams: { ...draftTask.generationParams, ...(patch.generationParams ?? {}) },
      };
      const next = insertTaskAfter(project.snapshot, savedTask, firstSceneId);
      onSnapshotChange(next);
      setSelectedTaskId(savedTask.id);
      closeEditor();
      return;
    }

    if (!editingTaskId) return;
    const { title, plannedDurationSeconds, ...composerPatch } = patch;
    let next = updateTaskComposerFields(project.snapshot, editingTaskId, composerPatch);
    next = {
      ...next,
      tasks: next.tasks.map((task) => task.id === editingTaskId
        ? {
            ...task,
            ...(typeof title === "string" && title.trim() ? { title: title.trim() } : {}),
            ...(typeof plannedDurationSeconds === "number" ? { plannedDurationSeconds } : {}),
          }
        : task),
    };
    onSnapshotChange(next);
    closeEditor();
  };

  return (
    <main className="project-workspace-page" aria-label="项目工作台">
      <header className="project-workspace-topbar">
        <button type="button" className="workspace-home-button" onClick={onBack} aria-label="返回项目首页"><Home size={18} /> 返回首页</button>
        <div className="workspace-project-title">
          <Folder size={24} />
          <strong>{project.title}</strong>
          <button type="button" aria-label="重命名项目" onClick={() => setRenameOpen(true)}><Pencil size={17} /></button>
        </div>
        <div className="workspace-top-actions">
          <button type="button" className="workspace-project-config-button" aria-label="项目配置" title="项目配置" onClick={() => setProjectConfigOpen(true)}><SlidersHorizontal size={18} /></button>
          <div className="workspace-view-switch" aria-label="任务视图">
            <button type="button" className={viewMode === "list" ? "is-active" : ""} onClick={() => setViewMode("list")}><List size={15} /> 表格</button>
            <span>/</span>
            <button type="button" className={viewMode === "card" ? "is-active" : ""} onClick={() => setViewMode("card")}><Grid2X2 size={15} /> 卡片</button>
          </div>
        </div>
      </header>

      <div className="project-workspace-body">
        <section className="project-task-area" aria-label="任务区域">
          <header className="task-workspace-toolbar">
            <Button variant="accent" onClick={openNewTask}><Plus size={15} /> 新建任务</Button>
            <span>{tasks.length} 个任务</span>
          </header>

          {viewMode === "list" ? (
            <div className="task-list-view">
              {tasks.length === 0 ? (
                <div className="task-list-empty"><p>当前项目还没有任务。</p></div>
              ) : tasks.map((task, index) => {
                const status = displayTaskStatus(task);
                const versions = resultCount(project.snapshot, task.id);
                return (
                  <ContextMenu key={task.id} actions={[{ label: "编辑任务", onSelect: () => openExistingEditor(task.id) }]}>
                    <button
                      type="button"
                      className={`task-list-row ${selectedTaskId === task.id ? "is-selected" : ""}`}
                      onClick={() => setSelectedTaskId(task.id)}
                      onDoubleClick={() => openExistingEditor(task.id)}
                    >
                      <TaskPreview previewUrl={taskPreview(project.snapshot, task)} compact />
                      <div className="task-list-copy">
                        <strong>#{index + 1} {task.title}</strong>
                        <span>提示词 {promptSummary(task)}</span>
                      </div>
                      <div className="task-list-stats">
                        <span>使用{task.assetBindings.length}个资产</span>
                        <span>{versions > 0 ? `${versions}个生成版本` : "无生成结果"}</span>
                      </div>
                      <div className={`task-list-status status-sticker is-${status}`}><i />{taskStatusLabel[status]}</div>
                    </button>
                  </ContextMenu>
                );
              })}
            </div>
          ) : (
            <div className="task-card-view">
              <button type="button" className="task-create-card" onClick={openNewTask}>
                <div><Plus className="creation-motion-icon" size={46} /></div>
                <strong>新建任务卡</strong>
              </button>

              {tasks.map((task, index) => {
                const status = displayTaskStatus(task);
                const versions = resultCount(project.snapshot, task.id);
                return (
                  <ContextMenu key={task.id} actions={[{ label: "编辑任务", onSelect: () => openExistingEditor(task.id) }]}>
                    <button
                      type="button"
                      className={`task-card-item ${selectedTaskId === task.id ? "is-selected" : ""}`}
                      onClick={() => setSelectedTaskId(task.id)}
                      onDoubleClick={() => openExistingEditor(task.id)}
                    >
                      <div className="task-card-preview-wrap">
                        <TaskPreview previewUrl={taskPreview(project.snapshot, task)} />
                        <span className={`task-card-status status-sticker is-${status}`}><i />{taskStatusLabel[status]}</span>
                      </div>
                      <strong>#{index + 1} {task.title}</strong>
                      <p>提示词 {promptSummary(task)}</p>
                      <footer>使用{task.assetBindings.length}个资产 · {versions > 0 ? `${versions}个生成版本` : "无生成结果"}</footer>
                    </button>
                  </ContextMenu>
                );
              })}
            </div>
          )}
        </section>

        <TaskInfoPanel
          snapshot={project.snapshot}
          task={selectedTask}
          onPlayResult={(result, task) => setPlaying({ result, task })}
        />
      </div>

      <footer className="project-workspace-statusbar">
        <button type="button" onClick={() => setSettingsOpen(true)}><Settings size={16} /> 设置</button>
        <div>
          {runningTask ? (
            <><span className="workspace-running-dot" />当前运行：{project.title} · 任务名：{runningTask.title}</>
          ) : (
            <><span className="workspace-idle-dot" />当前没有正在运行的任务</>
          )}
        </div>
      </footer>

      <TaskEditorDialog
        open={Boolean(editingTask)}
        task={editingTask}
        assets={project.snapshot.assets}
        projectContext={{
          description: project.description,
          useDescriptionForAiPrompt: project.useDescriptionForAiPrompt,
        }}
        onClose={closeEditor}
        onSave={saveTask}
      />

      <ProjectConfigDialog
        open={projectConfigOpen}
        project={project}
        onClose={() => setProjectConfigOpen(false)}
        onSave={(settings, assets) => {
          onUpdateProjectSettings(settings);
          onSnapshotChange({ ...project.snapshot, assets });
        }}
      />

      <Dialog open={renameOpen} icon="edit" title="重命名项目" onClose={() => setRenameOpen(false)}>
        <div className="project-simple-dialog">
          <label><span>项目名称</span><input autoFocus value={renameValue} onChange={(event) => setRenameValue(event.target.value)} /></label>
          <footer>
            <Button onClick={() => setRenameOpen(false)}>取消</Button>
            <Button variant="accent" onClick={() => {
              const next = renameValue.trim();
              if (next) onRenameProject(next);
              setRenameOpen(false);
            }}>保存</Button>
          </footer>
        </div>
      </Dialog>

      <Dialog open={Boolean(playing)} icon="video" title={playing ? `播放结果 · ${playing.task.title}` : "播放结果"} onClose={() => setPlaying(null)}>
        {playing && (
          <div className="task-playback-dialog">
            <video controls autoPlay={false} poster={playing.result.previewUrl} src={playing.result.videoUrl} />
            <footer><span>{playing.task.number}</span><Button onClick={() => setPlaying(null)}>关闭</Button></footer>
          </div>
        )}
      </Dialog>

      <Dialog open={settingsOpen} icon="settings" title="设置" onClose={() => setSettingsOpen(false)}>
        <div className="project-settings-placeholder">
          <Settings size={22} />
          <h3>应用设置</h3>
          <p>生成服务与应用级低频设置从这里进入；项目自身的信息和资产请使用右上角“项目配置”。</p>
          <Button onClick={() => setSettingsOpen(false)}>关闭</Button>
        </div>
      </Dialog>
    </main>
  );
}

export function CreateProjectDialog({
  open,
  onClose,
  onCreate,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (title: string) => void;
}) {
  const [title, setTitle] = useState("");

  useEffect(() => {
    if (open) setTitle("");
  }, [open]);

  return (
    <Dialog open={open} icon="create" title="新建项目" description="创建后进入项目工作台。" onClose={onClose}>
      <div className="project-simple-dialog">
        <label><span>项目名称</span><input autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：异星边境 初到基地" /></label>
        <footer>
          <Button onClick={onClose}>取消</Button>
          <Button variant="accent" disabled={!title.trim()} onClick={() => onCreate(title.trim())}><Check size={14} /> 创建项目</Button>
        </footer>
      </div>
    </Dialog>
  );
}
