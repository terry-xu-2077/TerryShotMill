import {
  ArrowLeft,
  Check,
  ChevronRight,
  Clock3,
  FileImage,
  Film,
  History,
  Link2,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Volume2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button, StatusPill } from "terry-react-ui-library";

import type { GenerationTaskCardView } from "../types";
import { Dialog, PortalSelect, useToast } from "../ui/overlay";
import { PromptAssetEditor, type PromptAsset } from "./PromptAssetEditor";
import { mockProjectAssets } from "../mock/assets";
import { getMockGenerationProfile, mockGenerationProfiles } from "../mock/generationProfiles";
import type { GenerationTask, TaskVisualBeat } from "../domain/storyboard";

type SaveState = "saved" | "saving" | "error";

const initialScript = "雨声渐密。她停在仓库门前，侧过脸听见门内传来的放映机转动声。门缝里透出一线暖光，她收起雨伞，伸手触碰生锈的门把。";
const initialIntent = "保持上一镜雨夜的冷色环境，但让门缝暖光成为视线焦点。镜头贴近人物侧脸，动作克制，不要突然推近。";
const initialAiPrompt = "Cinematic medium close-up at a rain-soaked harbor warehouse. The young woman pauses beneath the eaves, wet hair against her cheek, listening to the faint mechanical rhythm behind the door. Cold cyan ambient light surrounds her while a narrow warm beam leaks through the rusty doorway. Slow controlled dolly-in, shallow depth of field, restrained natural movement. Maintain character, wardrobe, rain direction, and lens continuity from the previous shot.";
const initialFinalPrompt = "Cinematic medium close-up at the rain-soaked warehouse entrance. She pauses under the eaves and turns slightly toward the warm light leaking through the door. Keep the previous shot's character, wardrobe, rain direction and 50mm lens continuity. Slow controlled dolly-in, shallow depth of field, restrained motion; no sudden camera acceleration.";

const defaultTaskAssets: Array<PromptAsset & { type: string; icon: typeof FileImage; sourcePath?: string }> = [
  { id: "asset-character", name: "林澜 · 雨夜造型", type: "Character", kind: "subject", reference: "<Subject 1>", detail: "角色素材", icon: FileImage, tone: "amber" },
  { id: "asset-scene", name: "旧港口仓库外景", type: "Scene", kind: "picture", reference: "<Picture 1>", detail: "场景素材", icon: FileImage, tone: "blue" },
  { id: "asset-motion", name: "撑伞收伞动作参考", type: "Video", kind: "video", reference: "<Video 1>", detail: "动作参考", icon: Film, tone: "green" },
  { id: "asset-audio", name: "雨声与远处汽笛", type: "Audio", kind: "audio", reference: "<Audio 1>", detail: "声音参考", icon: Volume2, tone: "violet" },
];

type TaskComposerPatch = Partial<Pick<GenerationTask,
  "scriptSource" | "userIntent" | "aiPrompt" | "finalPrompt" | "visualBeats" | "generationProfileId" | "generationProfileLabel"
>>;

export function TaskComposer({
  task,
  onClose,
  onTaskChange,
}: {
  task: GenerationTaskCardView;
  onClose: () => void;
  onTaskChange?: (patch: TaskComposerPatch) => void;
}) {
  const referenceCounts = { subject: 0, picture: 0, video: 0, audio: 0 };
  const boundTaskAssets: Array<PromptAsset & { type: string; icon: typeof FileImage; sourcePath?: string }> = (task.assetBindings ?? []).flatMap((binding) => {
    const asset = mockProjectAssets.find((item) => item.id === binding.assetId);
    if (!asset) return [];
    const kind: PromptAsset["kind"] = binding.role === "character"
      ? "subject"
      : asset.mediaType === "video"
        ? "video"
        : asset.mediaType === "audio"
          ? "audio"
          : "picture";
    referenceCounts[kind] += 1;
    const label = kind === "subject" ? "Subject" : kind[0].toUpperCase() + kind.slice(1);
    const icon = kind === "video" ? Film : kind === "audio" ? Volume2 : FileImage;
    return [{
      id: asset.id,
      name: asset.name,
      type: `${asset.mediaType} · ${asset.category}`,
      kind,
      reference: `<${label} ${referenceCounts[kind]}>`,
      detail: `${binding.role} · ${asset.projectRelativePath}`,
      icon,
      tone: kind === "subject" ? "amber" : kind === "video" ? "green" : kind === "audio" ? "violet" : "blue",
      sourcePath: asset.projectRelativePath,
    }];
  });
  const taskAssets = boundTaskAssets.length > 0 ? boundTaskAssets : defaultTaskAssets;
  const [scriptSource, setScriptSource] = useState(task.scriptSource ?? initialScript);
  const [userIntent, setUserIntent] = useState(task.userIntent ?? initialIntent);
  const [aiPrompt, setAiPrompt] = useState(task.aiPrompt ?? initialAiPrompt);
  const [finalPrompt, setFinalPrompt] = useState(task.finalPrompt ?? initialFinalPrompt);
  const [generationProfile, setGenerationProfile] = useState(task.generationProfileId ?? "profile-h3-multi-shot");
  const [visualBeats, setVisualBeats] = useState<TaskVisualBeat[]>(task.visualBeats?.map((beat) => ({ ...beat })) ?? []);
  const [selectedBeatId, setSelectedBeatId] = useState(task.visualBeats?.[0]?.id ?? "");
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [promptGenerating, setPromptGenerating] = useState(false);
  const [revision, setRevision] = useState(2);
  const [revisionOpen, setRevisionOpen] = useState(false);
  const [replaceConfirmOpen, setReplaceConfirmOpen] = useState(false);
  const [remoteProgress, setRemoteProgress] = useState(task.progress ?? 43);
  const saveTimer = useRef<number | null>(null);
  const promptTimer = useRef<number | null>(null);
  const pushToast = useToast();
  const beatSequence = useRef(visualBeats.length);
  const selectedBeat = visualBeats.find((beat) => beat.id === selectedBeatId);
  const profile = getMockGenerationProfile(generationProfile);
  const plannedDuration = Number.parseFloat(task.plannedDurationLabel) || 0;
  const capabilityWarnings = [
    visualBeats.length > 1 && !profile.capability.multiShotPrompt ? "当前 Profile 不支持多镜头提示词。" : "",
    profile.capability.maxDurationSeconds && plannedDuration > profile.capability.maxDurationSeconds
      ? `Task 计划时长超过 Profile 上限 ${profile.capability.maxDurationSeconds}s。`
      : "",
  ].filter(Boolean);

  useEffect(() => {
    const remoteTimer = window.setTimeout(() => setRemoteProgress((progress) => Math.min(99, progress + 4)), 650);
    return () => window.clearTimeout(remoteTimer);
  }, []);

  useEffect(() => () => {
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    if (promptTimer.current) window.clearTimeout(promptTimer.current);
  }, []);

  const scheduleSave = () => {
    setSaveState("saving");
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => setSaveState("saved"), 420);
  };

  const updateField = (setter: (value: string) => void, value: string, patch?: TaskComposerPatch) => {
    setter(value);
    if (patch) onTaskChange?.(patch);
    scheduleSave();
  };

  const regenerateAiPrompt = () => {
    if (promptGenerating) return;
    setPromptGenerating(true);
    promptTimer.current = window.setTimeout(() => {
      const nextRevision = revision + 1;
      setRevision(nextRevision);
      const nextPrompt = `${initialAiPrompt} Preserve the hand reaching toward the handle as the final beat. [AI revision ${nextRevision}]`;
      setAiPrompt(nextPrompt);
      onTaskChange?.({ aiPrompt: nextPrompt });
      setPromptGenerating(false);
      pushToast("新的 AI Prompt 已生成，Final Prompt 保持不变", "success");
    }, 360);
  };

  const replaceFinalPrompt = () => {
    setFinalPrompt(aiPrompt);
    onTaskChange?.({ finalPrompt: aiPrompt });
    setReplaceConfirmOpen(false);
    scheduleSave();
    pushToast("已用当前 AI Prompt 替换 Final Prompt", "success");
  };

  const updateVisualBeats = (next: TaskVisualBeat[]) => {
    setVisualBeats(next);
    onTaskChange?.({ visualBeats: next });
    scheduleSave();
  };

  const patchSelectedBeat = (patch: Partial<TaskVisualBeat>) => {
    if (!selectedBeat) return;
    updateVisualBeats(visualBeats.map((beat) => beat.id === selectedBeat.id ? { ...beat, ...patch } : beat));
  };

  const addVisualBeat = () => {
    beatSequence.current += 1;
    const id = `${task.id}-beat-local-${beatSequence.current}`;
    const previousEnd = visualBeats.at(-1)?.plannedEnd ?? plannedDuration;
    const beat: TaskVisualBeat = {
      id,
      label: `Beat ${visualBeats.length + 1}`,
      description: "等待补充镜头描述。",
      plannedStart: previousEnd,
      plannedEnd: previousEnd + 3,
    };
    updateVisualBeats([...visualBeats, beat]);
    setSelectedBeatId(id);
  };

  const moveSelectedBeat = (delta: number) => {
    const index = visualBeats.findIndex((beat) => beat.id === selectedBeatId);
    const target = index + delta;
    if (index < 0 || target < 0 || target >= visualBeats.length) return;
    const next = [...visualBeats];
    [next[index], next[target]] = [next[target], next[index]];
    updateVisualBeats(next);
  };

  return (
    <div className="task-composer" data-testid="task-composer">
      <header className="composer-header">
        <button type="button" className="composer-back" onClick={onClose}><ArrowLeft size={17} /> 返回任务</button>
        <div className="composer-title">
          <span className="eyebrow">TASK COMPOSER</span>
          <h1>{task.number} · {task.title}</h1>
          <p>剧本、AI 生成稿和人工确认稿保持独立。</p>
        </div>
        <div className="composer-save" data-testid="save-state" aria-live="polite">
          <span className={`save-dot state-${saveState}`} />
          <strong>{saveState === "saved" ? "已保存" : saveState === "saving" ? "保存中" : "保存失败"}</strong>
          <small>本地 Mock 草稿</small>
        </div>
      </header>

      <section className="composer-beat-strip" aria-label="Task Visual Beats">
        <header>
          <div><span className="eyebrow">TASK INTERNAL STRUCTURE</span><strong>Visual Beat Strip</strong></div>
          <small>{visualBeats.length > 1 ? `多镜头 Task · ${visualBeats.length} Beats` : visualBeats.length === 1 ? "单镜头 Task" : "镜头描述待规划"}</small>
        </header>
        <div className="composer-beat-tabs" role="tablist" aria-label="Visual Beats">
          {visualBeats.map((beat, index) => (
            <button key={beat.id} type="button" role="tab" aria-selected={beat.id === selectedBeatId} onClick={() => setSelectedBeatId(beat.id)}>
              <span>{index + 1}</span><strong>{beat.label}</strong><small>{beat.plannedStart ?? "—"}-{beat.plannedEnd ?? "—"}s</small>
            </button>
          ))}
          <button type="button" className="composer-add-beat" onClick={addVisualBeat}>+ 添加 Beat</button>
        </div>
        {selectedBeat && (
          <div className="composer-beat-editor">
            <label><span>Beat Label</span><input aria-label="Beat Label" value={selectedBeat.label} onChange={(event) => patchSelectedBeat({ label: event.target.value })} /></label>
            <label><span>镜头描述</span><textarea aria-label="Beat Description" rows={2} value={selectedBeat.description} onChange={(event) => patchSelectedBeat({ description: event.target.value })} /></label>
            <div>
              <button type="button" onClick={() => moveSelectedBeat(-1)}>向前移动</button>
              <button type="button" onClick={() => moveSelectedBeat(1)}>向后移动</button>
              <button type="button" onClick={() => {
                const index = visualBeats.findIndex((beat) => beat.id === selectedBeat.id);
                const next = visualBeats.filter((beat) => beat.id !== selectedBeat.id);
                updateVisualBeats(next);
                setSelectedBeatId(next[Math.min(index, next.length - 1)]?.id ?? "");
              }}>删除 Beat</button>
            </div>
          </div>
        )}
        {capabilityWarnings.length > 0 && <div className="composer-capability-warning" role="alert">{capabilityWarnings.map((warning) => <span key={warning}>{warning}</span>)}</div>}
      </section>

      <div className="composer-columns">
        <section className="composer-column script-column" aria-label="剧本与设置">
          <header><span>01</span><div><strong>剧本 / 设置</strong><small>创作输入与生成约束</small></div></header>
          <label className="composer-field">
            <span><strong>Script Source</strong><small>原始剧本</small></span>
            <textarea
              value={scriptSource}
              onChange={(event) => updateField(setScriptSource, event.target.value, { scriptSource: event.target.value })}
              aria-label="Script Source"
              rows={7}
            />
          </label>
          <label className="composer-field">
            <span><strong>User Intent</strong><small>镜头创作意图</small></span>
            <textarea
              value={userIntent}
              onChange={(event) => updateField(setUserIntent, event.target.value, { userIntent: event.target.value })}
              aria-label="User Intent"
              rows={5}
            />
          </label>
          <div className="composer-field">
            <span><strong>Generation Profile</strong><small>继承自项目默认设置</small></span>
            <PortalSelect
              value={generationProfile}
              onChange={(value) => {
                const nextProfile = getMockGenerationProfile(value);
                setGenerationProfile(value);
                onTaskChange?.({ generationProfileId: nextProfile.id, generationProfileLabel: nextProfile.label });
                scheduleSave();
              }}
              ariaLabel="Generation Profile"
              options={mockGenerationProfiles.map((item) => ({ value: item.id, label: item.label, detail: item.detail }))}
            />
          </div>
          <section className="composer-context">
            <div className="section-label"><strong>Task Context</strong><small>生成依赖，不是剪辑时间线</small></div>
            <div className="context-node"><span>S01-001</span><div><strong>上一任务</strong><small>Primary Result 02 · Visual + Semantic</small></div><ChevronRight size={15} /></div>
            <div className="context-current"><Link2 size={14} /><span>当前任务继承视觉连续性</span></div>
            <div className="context-node is-next"><span>S01-003</span><div><strong>下一任务</strong><small>计划：推门进入空旷大厅</small></div></div>
          </section>
        </section>

        <section className="composer-column prompt-column" aria-label="Prompt 编辑">
          <header><span>02</span><div><strong>Prompt</strong><small>AI 草稿与人工确认稿</small></div></header>
          <div className="prompt-block ai-prompt-block">
            <div className="prompt-block-head">
              <div><span className="prompt-kind ai"><Sparkles size={13} /> AI PROMPT</span><small>Revision {revision}</small></div>
              <div className="prompt-actions">
                <button type="button" onClick={() => setRevisionOpen(true)}><History size={14} /> Revision</button>
                <button type="button" onClick={regenerateAiPrompt} disabled={promptGenerating}><RefreshCw size={14} className={promptGenerating ? "is-spinning" : ""} /> {promptGenerating ? "生成中" : "重新生成"}</button>
              </div>
            </div>
            <textarea value={aiPrompt} readOnly aria-label="AI Prompt" rows={10} />
            <footer><span>AI 输出不会自动写入 Final Prompt</span><button type="button" onClick={() => setReplaceConfirmOpen(true)}>采用此版本</button></footer>
          </div>

          <div className="prompt-block final-prompt-block">
            <div className="prompt-block-head">
              <div><span className="prompt-kind final"><ShieldCheck size={13} /> FINAL PROMPT</span><small>人工确认 · 生成时使用</small></div>
              <StatusPill tone="active">READY</StatusPill>
            </div>
            <PromptAssetEditor
              value={finalPrompt}
              onChange={(value) => updateField(setFinalPrompt, value, { finalPrompt: value })}
              assets={taskAssets}
              ariaLabel="Final Prompt"
              rows={10}
            />
          </div>

          <section className="validator-panel" aria-label="Prompt Validator">
            <header><div><ShieldCheck size={16} /><strong>Validator</strong></div><StatusPill tone="active">3 PASS · 1 NOTE</StatusPill></header>
            <div className="validator-grid">
              <span className="is-pass"><Check size={13} /> Asset 引用有效</span>
              <span className="is-pass"><Check size={13} /> 时长 6 秒有效</span>
              <span className="is-pass"><Check size={13} /> 上游 Context 可用</span>
              <span className="is-note"><Clock3 size={13} /> Audio Reference 可选</span>
            </div>
          </section>
        </section>

        <section className="composer-column asset-column" aria-label="项目资产">
          <header><span>03</span><div><strong>项目资产</strong><small>当前任务已选择 {taskAssets.length} 项</small></div></header>
          <button type="button" className="asset-picker-entry">管理当前选择 <ChevronRight size={15} /></button>
          <div className="composer-assets">
            {taskAssets.map(({ id, name, type, icon: Icon, tone, sourcePath }) => (
              <article key={id} className="composer-asset-card">
                <div className={`asset-thumb tone-${tone}`}><Icon size={21} /><span>{type}</span></div>
                <div><strong title={name}>{name}</strong><small title={sourcePath}>{type} · 已绑定</small></div>
                <Check size={14} />
              </article>
            ))}
          </div>
          <section className="asset-usage-summary">
            <span className="eyebrow">REFERENCE MAP</span>
            {taskAssets.map((asset) => (
              <div key={asset.id}><span>{asset.reference}</span><strong title={asset.detail}>{asset.name}</strong></div>
            ))}
          </section>
          <section className="remote-update-card" data-testid="remote-progress">
            <div><span className="status-dot is-online" /><strong>后台状态已同步</strong></div>
            <p>Mock Job 进度更新为 {remoteProgress}%，编辑器节点保持不变。</p>
          </section>
        </section>
      </div>

      <Dialog open={replaceConfirmOpen} icon="replace" title="替换 Final Prompt？" description="人工编辑内容不会自动被覆盖。仅在你确认后执行本次替换。" onClose={() => setReplaceConfirmOpen(false)}>
        <div className="confirm-prompt-replace">
          <p>当前 Final Prompt 将被 Revision {revision} 的 AI Prompt 替换。</p>
          <div><Button onClick={() => setReplaceConfirmOpen(false)}>取消</Button><Button variant="accent" onClick={replaceFinalPrompt}>确认替换</Button></div>
        </div>
      </Dialog>

      <Dialog open={revisionOpen} icon="history" title="Prompt Revision" description="AI Prompt 的生成历史；Final Prompt 始终独立保存。" onClose={() => setRevisionOpen(false)}>
        <div className="revision-list">
          {[revision, revision - 1, 1].map((item, index) => (
            <button key={`${item}-${index}`} type="button" className={index === 0 ? "is-current" : ""}>
              <span>Revision {item}</span><strong>{index === 0 ? "当前 AI 版本" : "历史版本"}</strong><small>MiniMax API · H3 Prompt Skill v0.1</small>
            </button>
          ))}
        </div>
      </Dialog>
    </div>
  );
}
