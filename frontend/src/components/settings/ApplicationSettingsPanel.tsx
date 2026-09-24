import { ThemePaletteEditor } from "./ThemePaletteEditor";
import { Slider } from "../../ui/Slider";
import defaultSystemPromptPresets from "./systemPromptPresets.json";
import { Network, Palette, RefreshCw, Save, Sparkles, Trash2, Workflow } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, Checkbox, SegmentedControl, TextField } from "../../ui/primitives";
import { Select } from "../../ui/Select";
import { WorkflowPresetEditor } from "./WorkflowPresetEditor";
import { ThemeSwitch } from "../../ui/ThemeSwitch";

import type {
  ApplicationSettings,
  ComfyUISettings,
  ComfyUIWorkflow,
  ComfyUIWorkflowProfile,
  LocalInferenceSettings,
} from "../../gateways/projectGateway";

const presetOptions = [
  { value: "Empty - Nothing", label: "不使用预设" },
  { value: "Normal - Describe", label: "普通描述" },
  { value: "Prompt Style - Tags", label: "提示词风格 · 标签" },
  { value: "Prompt Style - Simple", label: "提示词风格 · 简洁" },
  { value: "Prompt Style - Detailed", label: "提示词风格 · 详细" },
  { value: "Prompt Style - Extreme Detailed", label: "提示词风格 · 极详细" },
  { value: "Prompt Style - Cinematic", label: "提示词风格 · 电影感" },
  { value: "Creative - Detailed Analysis", label: "创作 · 详细分析" },
  { value: "Creative - Summarize Video", label: "创作 · 总结视频" },
  { value: "Creative - Short Story", label: "创作 · 短故事" },
  { value: "Creative - Refine & Expand Prompt", label: "创作 · 优化提示词" },
  { value: "Vision - *Bounding Box", label: "视觉 · 边界框" },
];

const modeOptions = [
  { value: "images", label: "图片" },
  { value: "one by one", label: "逐张图片" },
  { value: "video", label: "视频帧" },
];

const seedModeOptions = [
  { value: "randomize", label: "每次随机" },
  { value: "fixed", label: "固定种子" },
];

const providerModeOptions = [
  { value: "local" as const, label: "本地推理" },
  { value: "api" as const, label: "API推理" },
];

const defaultLocalInferenceSettings: LocalInferenceSettings = {
  presetPrompt: "Empty - Nothing",
  inferenceMode: "images",
  maxFrames: 24,
  maxSize: 256,
  seedMode: "randomize",
  seed: 0,
  forceOffload: false,
  saveStates: false,
};

const defaultSystemPrompt = defaultSystemPromptPresets[0].prompt;
const defaultComfyUISettings: ComfyUISettings = {
  baseUrl: "http://127.0.0.1:8188",
  rootPath: "",
  workflowDirectory: "user/default/workflows",
  defaultProfileId: "",
  workflowProfiles: [],
};

export function ApplicationSettingsPanel({
  settings,
  onClose,
  onSave,
  onRefreshComfyUIWorkflows,
}: {
  settings?: ApplicationSettings;
  onClose: () => void;
  onSave: (settings: ApplicationSettings) => Promise<void>;
  onRefreshComfyUIWorkflows?: () => Promise<ComfyUIWorkflow[]>;
}) {
  const [draft, setDraft] = useState<LocalInferenceSettings>(defaultLocalInferenceSettings);
  const [section, setSection] = useState<"ai" | "connection" | "workflows" | "appearance">("ai");
  const [systemPrompt, setSystemPrompt] = useState(defaultSystemPrompt);
  const [systemPromptPresets, setSystemPromptPresets] = useState(defaultSystemPromptPresets);
  const [providerMode, setProviderMode] = useState<ApplicationSettings["providerMode"]>("local");
  const [apiBaseUrl, setApiBaseUrl] = useState("");
  const [apiModel, setApiModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiSupportsNativeVideo, setApiSupportsNativeVideo] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [selectedPresetId, setSelectedPresetId] = useState("");
  const [presetName, setPresetName] = useState("");
  const [comfyui, setComfyui] = useState<ComfyUISettings>(defaultComfyUISettings);
  const [workflows, setWorkflows] = useState<ComfyUIWorkflow[]>([]);
  const [workflowsLoading, setWorkflowsLoading] = useState(false);

  useEffect(() => {
    setDraft(settings ? structuredClone(settings.localInference) : structuredClone(defaultLocalInferenceSettings));
    setSystemPrompt(settings?.systemPrompt ?? defaultSystemPrompt);
    setSystemPromptPresets(settings?.systemPromptPresets ? structuredClone(settings.systemPromptPresets) : structuredClone(defaultSystemPromptPresets));
    setSelectedPresetId(settings?.systemPromptPresets.find((preset) => preset.prompt === settings.systemPrompt)?.id ?? settings?.systemPromptPresets[0]?.id ?? defaultSystemPromptPresets[0].id);
    setProviderMode(settings?.providerMode ?? "local");
    setApiBaseUrl(settings?.apiBaseUrl ?? "");
    setApiModel(settings?.apiModel ?? "");
    setApiKey(settings?.apiKey ?? "");
    setApiSupportsNativeVideo(settings?.apiSupportsNativeVideo ?? false);
    setComfyui(settings?.comfyui ? structuredClone(settings.comfyui) : structuredClone(defaultComfyUISettings));
    setWorkflows([]);
    setPresetName("");
    setError("");
  }, [settings]);

  const update = (patch: Partial<LocalInferenceSettings>) => setDraft((current) => ({ ...current, ...patch }));
  const updateComfyui = (patch: Partial<ComfyUISettings>) => setComfyui((current) => ({ ...current, ...patch }));
  const removeProfile = (id: string) => {
    const next = comfyui.workflowProfiles.filter((profile) => profile.id !== id);
    updateComfyui({ workflowProfiles: next, defaultProfileId: comfyui.defaultProfileId === id ? next[0]?.id ?? "" : comfyui.defaultProfileId });
  };
  const refreshWorkflows = async () => {
    if (!onRefreshComfyUIWorkflows) return;
    setWorkflowsLoading(true);
    try {
      setWorkflows(await onRefreshComfyUIWorkflows());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "无法读取工作流，请检查 Bridge 连接后重试。");
    } finally {
      setWorkflowsLoading(false);
    }
  };
  const selectPreset = (id: string) => {
    const preset = systemPromptPresets.find((item) => item.id === id);
    setSelectedPresetId(id);
    if (preset) setSystemPrompt(preset.prompt);
  };
  const savePreset = () => {
    const name = presetName.trim();
    if (!name || !systemPrompt.trim()) return;
    const existing = systemPromptPresets.find((item) => item.name === name);
    const preset = { id: existing?.id ?? `system-prompt-${Date.now()}`, name, prompt: systemPrompt };
    setSystemPromptPresets(existing
      ? systemPromptPresets.map((item) => item.id === existing.id ? preset : item)
      : [...systemPromptPresets, preset]);
    setSelectedPresetId(preset.id);
    setPresetName("");
  };
  const deletePreset = () => {
    if (systemPromptPresets.length <= 1) return;
    const next = systemPromptPresets.filter((item) => item.id !== selectedPresetId);
    const replacement = next[0];
    setSystemPromptPresets(next);
    setSystemPrompt(replacement.prompt);
    setSelectedPresetId(replacement.id);
  };
  const save = async (nextComfyui = comfyui, closeAfterSave = true): Promise<boolean> => {
    setSaving(true);
    setError("");
    try {
      await onSave({
        providerMode,
        systemPrompt,
        systemPromptPresets,
        apiBaseUrl,
        apiModel,
        apiKey,
        apiSupportsNativeVideo,
        localInference: draft,
        comfyui: nextComfyui,
      });
      if (closeAfterSave) onClose();
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "应用设置保存失败");
      return false;
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="application-settings-panel">
      <nav className="application-settings-nav" aria-label="设置栏目" role="tablist">
        {([
          { id: "ai", label: "AI 增强", icon: Sparkles },
          { id: "connection", label: "ComfyUI 通信", icon: Network },
          { id: "workflows", label: "生成工作流", icon: Workflow },
          { id: "appearance", label: "外观", icon: Palette },
        ] as const).map((item) => <button key={item.id} type="button" role="tab" aria-selected={section === item.id} aria-controls={`settings-${item.id}`} onClick={() => setSection(item.id)}><item.icon size={16} /><span>{item.label}</span></button>)}
      </nav>
      <div className="application-settings-content" role="tabpanel" id={`settings-${section}`}>
      {section === "appearance" && <section className="application-settings-section" aria-label="外观设置">
        <header><strong>外观</strong></header>
        <div className="application-settings-appearance"><span>界面主题</span><ThemeSwitch /></div>
        <ThemePaletteEditor />
      </section>}
      {section === "ai" && <section className="application-settings-section" aria-labelledby="ai-enhancement-settings-title">
        <header>
          <div>
            <strong id="ai-enhancement-settings-title">AI增强</strong>
            <span>通用系统提示词与推理方式</span>
          </div>
        </header>

        <SegmentedControl
          value={providerMode}
          options={providerModeOptions}
          onChange={setProviderMode}
          ariaLabel="AI增强推理方式"
          presentation="tabs"
          fluid
        />

        <div className="application-settings-grid application-settings-common-grid">
          <label className="application-settings-field application-settings-preset">
            <span>系统提示词预设</span>
            <div className="application-settings-preset-row">
              <Select value={selectedPresetId} options={systemPromptPresets.map((item) => ({ value: item.id, label: item.name }))} onChange={selectPreset} ariaLabel="系统提示词预设" />
              <Button disabled={systemPromptPresets.length <= 1} onClick={deletePreset}><Trash2 size={14} /> 删除</Button>
            </div>
          </label>
          <div className="application-settings-field application-settings-preset-save">
            <span>保存当前提示词为预设</span>
            <div className="application-settings-preset-row">
              <TextField value={presetName} onChange={setPresetName} placeholder="预设名称" />
              <Button disabled={!presetName.trim() || !systemPrompt.trim()} onClick={savePreset}><Save size={14} /> 保存预设</Button>
            </div>
          </div>
        </div>

        <label className="application-settings-field application-settings-system-prompt">
          <span>系统提示词</span>
          <textarea value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} spellCheck={false} />
        </label>

        {providerMode === "local" ? (
          <section className="application-settings-provider-section" aria-label="本地推理">
            <header><strong>本地推理</strong><span className="application-settings-provider">llama_cpp_instruct_adv</span></header>
            <div className="application-settings-grid">
              <label className="application-settings-field"><span>预设提示词</span><Select value={draft.presetPrompt} options={presetOptions} onChange={(value) => update({ presetPrompt: value })} ariaLabel="预设提示词" /></label>
              <label className="application-settings-field"><span>推理模式</span><Select value={draft.inferenceMode} options={modeOptions} onChange={(value) => update({ inferenceMode: value as LocalInferenceSettings["inferenceMode"] })} ariaLabel="推理模式" /></label>
              <label className="application-settings-field"><span>最大视频帧数</span><TextField value={String(draft.maxFrames)} onChange={(value) => update({ maxFrames: Math.max(2, Math.min(1024, Number(value) || 2)) })} /></label>
              <label className="application-settings-field application-settings-seed"><span>种子方式</span><Select value={draft.seedMode} options={seedModeOptions} onChange={(value) => update({ seedMode: value as LocalInferenceSettings["seedMode"] })} ariaLabel="种子方式" /></label>
              <label className="application-settings-field"><span>固定种子</span><TextField value={String(draft.seed)} disabled={draft.seedMode !== "fixed"} onChange={(value) => update({ seed: Math.max(0, Number(value) || 0) })} /></label>
            </div>
          </section>
        ) : (
          <section className="application-settings-provider-section" aria-label="API推理">
            <header><strong>API推理</strong><span>OpenAI 兼容接口</span></header>
            <div className="application-settings-grid">
              <label className="application-settings-field"><span>接口地址</span><TextField value={apiBaseUrl} onChange={setApiBaseUrl} placeholder="http://127.0.0.1:8000/v1" /></label>
              <label className="application-settings-field"><span>模型名称</span><TextField value={apiModel} onChange={setApiModel} placeholder="模型名称" /></label>
              <label className="application-settings-field"><span>API Key</span><TextField value={apiKey} onChange={setApiKey} placeholder="可选" /></label>
              <label className="application-settings-toggle"><span>支持原生视频输入</span><Checkbox checked={apiSupportsNativeVideo} onChange={setApiSupportsNativeVideo} ariaLabel="支持原生视频输入" /></label>
            </div>
          </section>
        )}

        {providerMode === "local" && <>
          <div className="application-settings-slider">
            <div><span>最大图片边长</span><strong>{draft.maxSize}px</strong></div>
            <Slider value={draft.maxSize} min={128} max={2048} step={64} allowOutOfRangeInput onChange={(value) => update({ maxSize: Math.max(128, Math.min(16384, value)) })} />
          </div>
          <div className="application-settings-toggles">
            <label><span>强制卸载模型</span><Checkbox checked={draft.forceOffload} onChange={(checked) => update({ forceOffload: checked })} ariaLabel="强制卸载模型" /></label>
            <label><span>保留会话状态</span><Checkbox checked={draft.saveStates} onChange={(checked) => update({ saveStates: checked })} ariaLabel="保留会话状态" /></label>
          </div>
        </>}
      </section>}

      {(section === "connection" || section === "workflows") && <section className="application-settings-section" aria-labelledby="comfyui-settings-title">
        <header>
          <div>
            <strong id="comfyui-settings-title">{section === "connection" ? "ComfyUI 通信" : "生成工作流"}</strong>
          </div>
          {section === "workflows" && <Button onClick={() => void refreshWorkflows()} disabled={workflowsLoading || !onRefreshComfyUIWorkflows}>
            <RefreshCw size={14} /> {workflowsLoading ? "读取中…" : "读取工作流"}
          </Button>}
        </header>
        {section === "connection" && <div className="application-settings-grid">
          <label className="application-settings-field"><span>服务地址</span><TextField value={comfyui.baseUrl} onChange={(value) => updateComfyui({ baseUrl: value })} placeholder="http://127.0.0.1:8188" /></label>
          <label className="application-settings-field"><span>ComfyUI 根目录</span><TextField value={comfyui.rootPath} onChange={(value) => updateComfyui({ rootPath: value })} placeholder="G:\\AIGC\\ComfyUI_Codex" /></label>
          <label className="application-settings-field"><span>工作流目录</span><TextField value={comfyui.workflowDirectory} onChange={(value) => updateComfyui({ workflowDirectory: value })} placeholder="user/default/workflows" /></label>
          <label className="application-settings-field"><span>默认生成档位</span><Select value={comfyui.defaultProfileId} options={[{ value: "", label: "未指定" }, ...comfyui.workflowProfiles.map((profile) => ({ value: profile.id, label: profile.name }))]} onChange={(value) => updateComfyui({ defaultProfileId: value })} ariaLabel="默认生成档位" /></label>
        </div>}
        {section === "workflows" && <>
        <WorkflowPresetEditor profiles={comfyui.workflowProfiles} workflows={workflows} busy={saving} onRemove={removeProfile} onSave={async (profile: ComfyUIWorkflowProfile) => {
          const next = { ...comfyui, defaultProfileId: comfyui.defaultProfileId || profile.id,
            workflowProfiles: comfyui.workflowProfiles.some((item) => item.id === profile.id)
              ? comfyui.workflowProfiles.map((item) => item.id === profile.id ? profile : item)
              : [...comfyui.workflowProfiles, profile] };
          const saved = await save(next, false);
          if (saved) setComfyui(next);
          return saved;
        }} />
        {workflows.length > 0 && <div className="application-settings-workflow-list">{workflows.map((workflow) => {
          const inputSummary = workflow.inputs.length > 0 ? <>
            <span>输入</span>
            {workflow.inputs.map((port, index) => <span className="application-settings-workflow-port" key={`${port.name}-${index}`}>
              <strong>{port.name}</strong>
              {port.portName && <small>{port.portName}</small>}
            </span>)}
          </> : "无外部输入";
          const outputSummary = workflow.outputs.length > 0
            ? `输出 ${workflow.outputs.map((port) => port.type).join("、")}`
            : "无输出标记";
          return <div key={workflow.id}><span>{workflow.name}</span><small className="application-settings-workflow-summary">{inputSummary} · {outputSummary}</small></div>;
        })}</div>}
        </>}
      </section>}
      </div>

      <footer className="application-settings-actions">
        {error && <p className="application-settings-error" role="alert">{error}</p>}
        <Button disabled={saving} onClick={onClose}>取消</Button>
        <Button variant="accent" disabled={saving} onClick={() => void save()}>{saving ? "保存中…" : "保存设置"}</Button>
      </footer>
    </div>
  );
}
