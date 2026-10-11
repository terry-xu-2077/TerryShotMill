import { useCallback, useEffect, useRef, useState } from "react";
import type { ProjectAsset } from "../../domain/storyboard";
import type { ProjectGateway, SaveTaskInput, TaskEditorView } from "../../gateways/projectGateway";
import type { LifecycleGateway } from "../../gateways/lifecycleGateway";
import { Button } from "../../ui/primitives";
import { Dialog } from "../../ui/overlay";
import type { DirectorProject } from "./projectTypes";

const FPS = 24;
type DirectorAsset = { id: string; name: string; kind: "image" | "video" | "audio"; number: number; previewUrl?: string; missing?: boolean; source: { type: string; path: string } };
type DirectorClip = {
  id: string; name: string; start: number; end: number; prompt: string; aiPrompt: string;
  promptMode: "user" | "ai"; refs: string[]; useGlobalPrompt: boolean;
  transitionMode: string; suspended: boolean; aiOptOut: boolean; aiMetadata: Record<string, unknown>;
};
type DirectorDocument = {
  version: number; fps: number; selected: string | null; globalPrompt: string;
  aiGlobalPrompt: string; globalPromptMode: string; globalAiMetadata: Record<string, unknown>;
  autoAiEnhance: boolean; clips: DirectorClip[]; assets: DirectorAsset[];
};
type RelinkCandidate = { name: string; path?: string; file?: File };
export type DirectorToolbarState = {
  readOnly: boolean; canEnhanceAll: boolean;
};

const assetKind = (asset: ProjectAsset): DirectorAsset["kind"] => asset.mediaType;
const token = (asset: DirectorAsset) => `<${asset.kind === "image" ? "Picture" : asset.kind === "video" ? "Video" : "Audio"} ${asset.number}>`;
const filename = (path: string) => path.split(/[\\/]/).at(-1) || path;
const projectAsset = (asset: ProjectAsset, number: number): DirectorAsset => ({
  id: asset.id, name: asset.name, kind: assetKind(asset), number,
  previewUrl: asset.previewUrl || asset.mediaUrl,
  source: { type: "shotmill-asset", path: asset.id },
});
const directorFields = (clip: DirectorClip) => ({
  useGlobalPrompt: clip.useGlobalPrompt, transitionMode: clip.transitionMode,
  suspended: clip.suspended, aiOptOut: clip.aiOptOut, aiMetadata: clip.aiMetadata,
});
const effectiveGlobal = (document: DirectorDocument) => document.globalPromptMode === "ai" && document.aiGlobalPrompt.trim()
  ? document.aiGlobalPrompt : document.globalPrompt;
const effectivePrompt = (document: DirectorDocument, clip: DirectorClip, local: string) =>
  [clip.useGlobalPrompt ? effectiveGlobal(document).trim() : "", local.trim()].filter(Boolean).join("\n\n");

function makeDocument(project: DirectorProject, timelineId: string, editors: Map<string, TaskEditorView>, selected: string | null): DirectorDocument {
  const root = project.director ?? {};
  const states = root.timelineStates && typeof root.timelineStates === "object" ? root.timelineStates as Record<string, Record<string, unknown>> : {};
  const timelineState = states[timelineId] ?? (timelineId === project.snapshot.scenes[0]?.id ? root : {});
  const director = { ...root, globalPrompt: "", aiGlobalPrompt: "", globalPromptMode: "user",
    globalAiMetadata: {}, autoAiEnhance: false, ...timelineState };
  const projectGlobal = director.globalPromptMode === "ai" && String(director.aiGlobalPrompt ?? "").trim()
    ? String(director.aiGlobalPrompt) : String(director.globalPrompt ?? "");
  const counters = { image: 0, video: 0, audio: 0 };
  const actual = new Map(project.snapshot.assets.map(asset => [asset.id, asset]));
  const layout = Array.isArray(root.assetLayout) ? root.assetLayout as { id: string; number: number }[] : null;
  const unresolved = new Map((Array.isArray(root.unresolvedAssets) ? root.unresolvedAssets as DirectorAsset[] : [])
    .map(asset => [asset.id, asset]));
  const assets = layout ? layout.flatMap(item => {
    const asset = actual.get(item.id);
    if (asset) return [projectAsset(asset, item.number)];
    const missing = unresolved.get(item.id);
    return missing ? [{ ...missing, missing: true }] : [];
  }) : project.snapshot.assets.map(asset => projectAsset(asset, ++counters[asset.mediaType]));
  if (layout) {
    const included = new Set(assets.map(asset => asset.id));
    for (const asset of assets) counters[asset.kind] = Math.max(counters[asset.kind], asset.number);
    for (const asset of project.snapshot.assets) {
      if (!included.has(asset.id)) assets.push(projectAsset(asset, ++counters[asset.mediaType]));
    }
  }
  const byId = new Map(assets.map(asset => [asset.id, asset]));
  let next = 0;
  const clips = project.snapshot.tasks.map(task => {
    const editor = editors.get(task.id);
    const start = Math.round((task.timelineStartSeconds ?? next) * FPS);
    const end = start + Math.max(1, Math.round(task.plannedDurationSeconds * FPS));
    next = Math.max(next, end);
    const meta = editor?.generation.director ?? {};
    const references = new Map(editor?.assetBindings.map(binding => [binding.reference, byId.get(binding.assetId)]) ?? []);
    const localToGlobal = (prompt: string) => prompt.replace(/<(?:Picture|Video|Audio|Subject)\s+\d+>/gi, label => {
      const asset = references.get(label);
      return asset ? token(asset) : label;
    });
    const changedUser = typeof meta.composedUserPrompt === "string" && meta.composedUserPrompt !== editor?.userPrompt;
    const changedAi = typeof meta.composedAiPrompt === "string" && meta.composedAiPrompt !== editor?.aiEnhancedPrompt;
    const activeChanged = editor?.promptSource === "ai" ? changedAi : changedUser;
    const activePrompt = editor?.promptSource === "ai" ? editor?.aiEnhancedPrompt ?? "" : editor?.userPrompt ?? "";
    const prefix = `${projectGlobal.trim()}\n\n`;
    const useGlobalPrompt = meta.useGlobalPrompt !== false && !(activeChanged && projectGlobal.trim() && !activePrompt.startsWith(prefix));
    const localPrompt = typeof meta.localPrompt === "string" && !changedUser
      ? meta.localPrompt : changedUser && useGlobalPrompt && editor?.userPrompt.startsWith(prefix)
        ? editor.userPrompt.slice(prefix.length) : editor?.userPrompt ?? "";
    const localAiPrompt = typeof meta.localAiPrompt === "string" && !changedAi
      ? meta.localAiPrompt : changedAi && useGlobalPrompt && editor?.aiEnhancedPrompt.startsWith(prefix)
        ? editor.aiEnhancedPrompt.slice(prefix.length) : editor?.aiEnhancedPrompt ?? "";
    return {
      id: task.id, name: editor?.title ?? task.title, start, end,
      prompt: localToGlobal(localPrompt),
      aiPrompt: localToGlobal(localAiPrompt),
      promptMode: editor?.promptSource ?? "user",
      refs: editor?.assetBindings.map(binding => binding.assetId).filter(id => byId.has(id)) ?? [],
      useGlobalPrompt,
      transitionMode: typeof meta.transitionMode === "string" ? meta.transitionMode : "tail_reference",
      suspended: meta.suspended === true, aiOptOut: meta.aiOptOut === true,
      aiMetadata: meta.aiMetadata && typeof meta.aiMetadata === "object" ? meta.aiMetadata as Record<string, unknown> : {},
    } satisfies DirectorClip;
  });
  return {
    version: 2, fps: FPS, selected: clips.some(clip => clip.id === selected) ? selected : clips[0]?.id ?? null,
    globalPrompt: String(director.globalPrompt ?? ""), aiGlobalPrompt: String(director.aiGlobalPrompt ?? ""),
    globalPromptMode: String(director.globalPromptMode ?? "user"),
    globalAiMetadata: director.globalAiMetadata && typeof director.globalAiMetadata === "object" ? director.globalAiMetadata as Record<string, unknown> : {},
    autoAiEnhance: false, clips, assets,
  };
}

function clipInput(document: DirectorDocument, clip: DirectorClip, knownAssets: Set<string>, editor?: TaskEditorView): SaveTaskInput {
  const assets = document.assets.filter(asset => !asset.missing && knownAssets.has(asset.id));
  const byId = new Map(assets.map(asset => [asset.id, asset]));
  const userPrompt = effectivePrompt(document, clip, clip.prompt);
  const aiPrompt = effectivePrompt(document, clip, clip.aiPrompt);
  const referencedIds = new Set(clip.refs);
  for (const asset of assets) if (userPrompt.includes(token(asset)) || aiPrompt.includes(token(asset))) referencedIds.add(asset.id);
  const bindings = [...referencedIds].flatMap(id => {
    const asset = byId.get(id);
    return asset ? [{ assetId: id, reference: token(asset), role: "reference" }] : [];
  });
  const generation = editor?.generation ?? {
    resolution: "1080p", quality: "标准", mode: "全能参考", contextMode: "不承接",
  };
  return {
    title: clip.name, summary: editor?.summary ?? "", scriptSource: editor?.scriptSource ?? "",
    userIntent: editor?.userIntent ?? "", userPrompt, aiEnhancedPrompt: aiPrompt,
    promptSource: clip.promptMode, durationSeconds: (clip.end - clip.start) / FPS,
    generation: { ...generation, director: { ...directorFields(clip), localPrompt: clip.prompt,
      localAiPrompt: clip.aiPrompt, composedUserPrompt: userPrompt, composedAiPrompt: aiPrompt } },
    assetBindings: bindings, editorPreference: editor?.editorPreference ?? { userViewMode: "visual", aiViewMode: "visual" },
    revision: editor?.revision,
  };
}

function normalizeImportedDocument(project: DirectorProject, document: DirectorDocument): DirectorDocument {
  const available = project.snapshot.assets;
  const byId = new Map(available.map(asset => [asset.id, asset]));
  const used = new Set<string>();
  const remapped = new Map<string, string>();
  const assets = document.assets.map((entry, index): DirectorAsset => {
    const original = filename(entry.source?.path || entry.name);
    const direct = entry.source?.type === "shotmill-asset" ? byId.get(entry.id) : undefined;
    const candidates = available.filter(asset => asset.mediaType === entry.kind &&
      (asset.originalFilename === original || asset.name === original) && !used.has(asset.id));
    const matched = direct?.mediaType === entry.kind ? direct : candidates.length === 1 ? candidates[0] : undefined;
    if (matched && !used.has(matched.id)) {
      used.add(matched.id);
      remapped.set(entry.id, matched.id);
      return projectAsset(matched, entry.number);
    }
    return { id: entry.id || `missing-${index + 1}`, name: entry.name || original,
      kind: entry.kind, number: entry.number, missing: true,
      source: { type: "missing", path: entry.source?.path || entry.name } };
  });
  const counters = { image: 0, video: 0, audio: 0 };
  for (const asset of assets) counters[asset.kind] = Math.max(counters[asset.kind], asset.number);
  for (const asset of available) {
    if (!used.has(asset.id)) assets.push(projectAsset(asset, ++counters[asset.mediaType]));
  }
  return { ...document, autoAiEnhance: false, assets, clips: document.clips.map(clip => ({ ...clip,
    refs: clip.refs.map(id => remapped.get(id) || id),
  })) };
}

export function DirectorWorkspace({ project, timelineId, gateway, lifecycleGateway, onChooseLocalFiles, onRefresh, selectedId, onSelection, onDirtyChange, onDuration, onToolbarChange, onGenerate, onClose }: {
  project: DirectorProject;
  timelineId: string;
  gateway: ProjectGateway;
  lifecycleGateway?: LifecycleGateway;
  onChooseLocalFiles?: () => Promise<string[]>;
  onRefresh: () => Promise<void>;
  selectedId: string | null;
  onSelection: (id: string | null) => void;
  onDirtyChange: (dirty: boolean) => void;
  onDuration: (timecode: string) => void;
  onToolbarChange: (state: DirectorToolbarState) => void;
  onGenerate: (ids: string[]) => Promise<void>;
  onClose: () => void;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const editors = useRef(new Map<string, TaskEditorView>());
  const baseline = useRef<DirectorDocument | null>(null);
  const loadedProjectId = useRef<string | null>(null);
  const selectedIdRef = useRef(selectedId);
  selectedIdRef.current = selectedId;
  const createdIds = useRef(new Map<string, string>());
  const importedAssetIds = useRef(new Set<string>());
  const replacingTimeline = useRef(false);
  const pendingImportedDocument = useRef<DirectorDocument | null>(null);
  const saving = useRef(false);
  const dirty = useRef(false);
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [importApproval, setImportApproval] = useState<DirectorDocument | null>(null);
  const send = useCallback((message: Record<string, unknown>) => frame.current?.contentWindow?.postMessage(message, location.origin), []);
  useEffect(() => {
    const requestSave = () => send({ type: "terrydirector:request-save" });
    const directorAction = (event: Event) => send({ type: "shotmill:action", action: (event as CustomEvent<string>).detail });
    window.addEventListener("shotmill:director-save-request", requestSave);
    window.addEventListener("shotmill:director-action", directorAction);
    return () => {
      window.removeEventListener("shotmill:director-save-request", requestSave);
      window.removeEventListener("shotmill:director-action", directorAction);
      if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    };
  }, [send]);

  const scheduleAutoSave = useCallback(() => {
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    autoSaveTimer.current = setTimeout(() => {
      autoSaveTimer.current = null;
      if (!dirty.current) return;
      if (saving.current) { scheduleAutoSave(); return; }
      send({ type: "terrydirector:request-save" });
    }, 1000);
  }, [send]);

  useEffect(() => {
    if (!ready || dirty.current || saving.current || loadedProjectId.current === project.id) return;
    let cancelled = false;
    setError("");
    void Promise.all(project.snapshot.tasks.map(task => gateway.getTaskEditor(project.id, task.id)))
      .then(items => {
        if (cancelled) return;
        editors.current = new Map(items.map(item => [item.id, item]));
        const document = makeDocument(project, timelineId, editors.current, selectedIdRef.current);
        baseline.current = document;
        loadedProjectId.current = project.id;
        if (pendingImportedDocument.current) {
          send({ type: "shotmill:import-result", document: pendingImportedDocument.current });
          pendingImportedDocument.current = null;
        } else if (!replacingTimeline.current && !dirty.current) {
          send({ type: "terrydirector:load", document });
        }
        send({ type: "terrydirector:ai-config", config: { shotmill: true }, status: "active" });
        send({ type: "terrydirector:activity", activity: { readonly: project.readOnly === true,
          clips: Object.fromEntries(project.snapshot.tasks.map(task => [task.id, {
            status: task.state === "running" ? "running" : task.state === "failed" ? "error" : task.state === "completed" ? "completed" : "idle",
            progress: (project.taskTimings?.[task.id]?.generationProgress?.percent ?? task.progress ?? 0) / 100,
          }])) } });
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : "无法读取片段编辑内容"));
    return () => { cancelled = true; };
  }, [ready, project, timelineId, gateway, send]);
  useEffect(() => {
    if (!ready) return;
    send({ type: "shotmill:previews", previews: Object.fromEntries(project.snapshot.tasks
      .filter(task => task.storyboardFrame.previewUrl)
      .map(task => [task.id, task.storyboardFrame.previewUrl])) });
    send({ type: "terrydirector:activity", activity: { readonly: project.readOnly === true,
      clips: Object.fromEntries(project.snapshot.tasks.map(task => [task.id, {
        status: task.state === "running" ? "running" : task.state === "failed" ? "error" : task.state === "completed" ? "completed" : "idle",
        progress: (project.taskTimings?.[task.id]?.generationProgress?.percent ?? task.progress ?? 0) / 100,
      }])) } });
  }, [ready, project, send]);

  const save = useCallback(async (document: DirectorDocument): Promise<Record<string, string>> => {
    if (saving.current) throw new Error("工程正在保存，请稍候");
    if (document.fps !== FPS) throw new Error("时间线帧率不匹配");
    saving.current = true;
    try {
      const before = baseline.current;
      if (!before) throw new Error("工程尚未加载完成");
      const original = new Map(before.clips.map(clip => [clip.id, clip]));
      const originalAssets = new Set(before.assets.filter(asset => !asset.missing).map(asset => asset.id));
      const knownAssets = new Set([...originalAssets, ...project.snapshot.assets.map(asset => asset.id), ...importedAssetIds.current]);
      const idMap: Record<string, string> = {};
      for (const clip of document.clips) {
        if (clip.end <= clip.start || clip.start < 0) throw new Error(`片段「${clip.name}」的时间范围无效`);
        const existingId = createdIds.current.get(clip.id) ?? clip.id;
        const editor = editors.current.get(existingId);
        const input = clipInput(document, clip, knownAssets, editor);
        if (!editor) {
          const result = await gateway.createTask(project.id, { ...input, timelineId });
          createdIds.current.set(clip.id, result.id);
          idMap[clip.id] = result.id;
          editors.current.set(result.id, await gateway.getTaskEditor(project.id, result.id));
        } else {
          const previous = original.get(existingId);
          const globalChanged = JSON.stringify({ prompt: before.globalPrompt, ai: before.aiGlobalPrompt, mode: before.globalPromptMode })
            !== JSON.stringify({ prompt: document.globalPrompt, ai: document.aiGlobalPrompt, mode: document.globalPromptMode });
          if (!previous || (globalChanged && clip.useGlobalPrompt) || JSON.stringify({ ...previous, start: 0, end: 0 }) !== JSON.stringify({ ...clip, id: existingId, start: 0, end: 0 })) {
            await gateway.updateTask(project.id, existingId, input);
            editors.current.set(existingId, await gateway.getTaskEditor(project.id, existingId));
          }
        }
      }
      for (const clip of document.clips) {
        const id = idMap[clip.id] ?? createdIds.current.get(clip.id) ?? clip.id;
        const previous = original.get(id);
        if (!previous || previous.start !== clip.start || previous.end !== clip.end) {
          await gateway.updateTaskTimeline(project.id, id, {
            startSeconds: clip.start / FPS, durationSeconds: (clip.end - clip.start) / FPS,
          });
          editors.current.set(id, await gateway.getTaskEditor(project.id, id));
        }
      }
      const timelineState = {
        globalPrompt: document.globalPrompt, aiGlobalPrompt: document.aiGlobalPrompt,
        globalPromptMode: document.globalPromptMode, globalAiMetadata: document.globalAiMetadata,
        autoAiEnhance: false,
      };
      const root = project.director ?? {};
      const states = root.timelineStates && typeof root.timelineStates === "object" ? root.timelineStates as Record<string, unknown> : {};
      const director = {
        ...root,
        timelineStates: { ...states, [timelineId]: timelineState },
        assetLayout: document.assets.map(asset => ({ id: asset.id, number: asset.number })),
        unresolvedAssets: document.assets.filter(asset => asset.missing || !knownAssets.has(asset.id))
          .map(asset => ({ ...asset, missing: true, previewUrl: undefined })),
      };
      if (JSON.stringify(director) !== JSON.stringify(project.director ?? {})) {
        await gateway.updateProject(project.id, { director });
      }
      const remaining = new Set(document.clips.map(clip => idMap[clip.id] ?? createdIds.current.get(clip.id) ?? clip.id));
      const removed = before.clips.map(clip => clip.id).filter(id => !remaining.has(id));
      if (removed.length) {
        if (!lifecycleGateway) throw new Error("当前工程无法移除片段");
        await lifecycleGateway.deleteTasks(project.id, removed);
        for (const id of removed) editors.current.delete(id);
      }
      if (!replacingTimeline.current) {
        for (const assetId of new Set([...before.assets.filter(asset => !asset.missing).map(asset => asset.id), ...importedAssetIds.current])) {
          if (!document.assets.some(item => item.id === assetId)) {
            await gateway.deleteAsset(project.id, assetId);
            importedAssetIds.current.delete(assetId);
          }
        }
      }
      baseline.current = { ...document, selected: document.selected ? idMap[document.selected] ?? document.selected : null,
        clips: document.clips.map(clip => ({ ...clip, id: idMap[clip.id] ?? clip.id })) };
      createdIds.current.clear();
      replacingTimeline.current = false;
      await onRefresh();
      return idMap;
    } finally { saving.current = false; }
  }, [project, timelineId, gateway, lifecycleGateway, onRefresh]);

  const relink = useCallback(async (document: DirectorDocument, targetId: string, selected: RelinkCandidate[]) => {
    const missing = document.assets.filter(asset => asset.missing);
    const target = missing.find(asset => asset.id === targetId);
    if (!target || !selected.length) return;
    const chosen = selected.find(item => item.name === filename(target.source.path)) || selected[0];
    const directory = chosen.path?.replace(/[\\/][^\\/]+$/, "");
    const byName = new Map(selected.map(item => [item.name, item]));
    const matches: { oldId: string; asset: DirectorAsset }[] = [];
    for (const placeholder of [target, ...missing.filter(asset => asset.id !== target.id)]) {
      const originalName = filename(placeholder.source.path);
      const candidate = placeholder.id === target.id ? chosen : byName.get(originalName) ||
        (directory ? { name: originalName, path: `${directory}\\${originalName}` } : undefined);
      if (!candidate) continue;
      try {
        const input = { name: placeholder.name, category: "reference" as const, tags: [] };
        const asset = candidate.path
          ? await gateway.importLocalAsset(project.id, candidate.path, input)
          : await gateway.importAsset(project.id, candidate.file!, input);
        if (asset.mediaType !== placeholder.kind) {
          await gateway.deleteAsset(project.id, asset.id);
          throw new Error(`「${candidate.name}」的媒体类型与「${placeholder.name}」不一致`);
        }
        importedAssetIds.current.add(asset.id);
        matches.push({ oldId: placeholder.id, asset: projectAsset(asset, placeholder.number) });
      } catch (reason) {
        if (placeholder.id === target.id) throw reason;
      }
    }
    send({ type: "shotmill:relink-result", matches });
    await onRefresh();
  }, [gateway, project.id, onRefresh, send]);

  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (event.origin !== location.origin || event.source !== frame.current?.contentWindow) return;
      const message = event.data ?? {};
      if (message.type === "terrydirector:ready") {
        setReady(true);
        send({ type: "shotmill:capabilities", localFilePaths: Boolean(onChooseLocalFiles) });
      }
      else if (message.type === "terrydirector:dirty") {
        dirty.current = Boolean(message.dirty);
        onDirtyChange(dirty.current);
        if (dirty.current) scheduleAutoSave();
        else if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
      }
      else if (message.type === "shotmill:duration") onDuration(String(message.timecode));
      else if (message.type === "shotmill:toolbar-state") onToolbarChange({
        readOnly: Boolean(message.readOnly), canEnhanceAll: Boolean(message.canEnhanceAll),
      });
      else if (message.type === "shotmill:import-timeline") {
        const imported = normalizeImportedDocument(project, message.document as DirectorDocument);
        if (project.snapshot.tasks.length) setImportApproval(imported);
        else {
          replacingTimeline.current = true;
          if (baseline.current) send({ type: "shotmill:import-result", document: imported });
          else pendingImportedDocument.current = imported;
        }
      }
      else if (message.type === "shotmill:relink-asset") {
        if (!onChooseLocalFiles) return;
        void onChooseLocalFiles().then(paths => relink(message.document as DirectorDocument, String(message.assetId),
          paths.map(path => ({ name: filename(path), path }))))
          .catch(reason => send({ type: "shotmill:relink-result", error: String(reason instanceof Error ? reason.message : reason ?? "重新链接失败") }));
      }
      else if (message.type === "shotmill:relink-files") {
        void relink(message.document as DirectorDocument, String(message.assetId),
          Array.from(message.files as File[]).map(file => ({ name: file.name, file })))
          .catch(reason => send({ type: "shotmill:relink-result", error: String(reason instanceof Error ? reason.message : reason ?? "重新链接失败") }));
      }
      else if (message.type === "shotmill:select") onSelection(message.taskId ?? null);
      else if (message.type === "shotmill:close") onClose();
      else if (message.type === "terrydirector:save") {
        if (saving.current) { scheduleAutoSave(); return; }
        void save(message.document).then(idMap => { setSaveError(""); send({ type: "shotmill:save-result", ok: true, idMap, revision: message.revision }); })
          .catch(reason => { const detail = reason instanceof Error ? reason.message : "保存失败"; setSaveError(detail); send({ type: "shotmill:save-result", ok: false, error: detail, revision: message.revision }); });
      } else if (message.type === "shotmill:generate") {
        void save(message.document).then(async idMap => {
          send({ type: "shotmill:save-result", ok: true, idMap });
          const ids = message.document.clips.filter((clip: DirectorClip) => !clip.suspended)
            .map((clip: DirectorClip) => idMap[clip.id] ?? clip.id);
          await onGenerate(ids);
        }).catch(reason => send({ type: "shotmill:save-result", ok: false, error: reason instanceof Error ? reason.message : "提交失败" }));
      } else if (message.type === "shotmill:enhance") {
        const document = message.document as DirectorDocument;
        const ids = (message.clipIds as string[] ?? []).filter(id => document.clips.some(clip => clip.id === id));
        if (!ids.length) return;
        void save(document).then(async idMap => {
          send({ type: "shotmill:save-result", ok: true, idMap });
          const taskIds = ids.map(id => idMap[id] ?? id);
          if (taskIds.length > 1) {
            await gateway.batchEnhancePrompts(project.id, { taskIds, includeProjectBackground: false, includePreviousTaskSummary: false });
            send({ type: "shotmill:enhance-result", notice: `已提交 ${taskIds.length} 个片段的 AI 增强` });
          } else {
            const clip = document.clips.find(item => item.id === ids[0])!;
            const editor = await gateway.getTaskEditor(project.id, taskIds[0]);
            const result = await gateway.enhancePrompt(project.id, {
              taskId: taskIds[0], isDraft: false, userPrompt: effectivePrompt(document, clip, clip.prompt),
              assets: clip.refs.flatMap(id => {
                const asset = document.assets.find(item => item.id === id);
                return asset ? [{ id, name: asset.name, reference: token(asset), kind: asset.kind === "image" ? "picture" as const : asset.kind }] : [];
              }),
              generation: { resolution: editor.generation.resolution, quality: editor.generation.quality,
                mode: editor.generation.mode, durationSeconds: (clip.end - clip.start) / FPS,
                contextMode: editor.generation.contextMode },
            });
            send({ type: "shotmill:enhance-result", clipId: taskIds[0], prompt: result.prompt });
          }
          await onRefresh();
        }).catch(reason => send({ type: "shotmill:enhance-result", error: reason instanceof Error ? reason.message : "AI 增强失败" }));
      } else if (message.type === "shotmill:enhance-global") {
        const document = message.document as DirectorDocument;
        void gateway.enhancePrompt(project.id, {
          taskId: document.selected ?? "", isDraft: true, userPrompt: document.globalPrompt,
          assets: document.assets.filter(asset => document.globalPrompt.includes(token(asset)))
            .map(asset => ({ id: asset.id, name: asset.name, reference: token(asset),
              kind: asset.kind === "image" ? "picture" as const : asset.kind })),
          generation: { resolution: "1080p", quality: "标准", mode: "全能参考", durationSeconds: 10, contextMode: "不承接" },
        }).then(result => send({ type: "shotmill:enhance-result", globalPrompt: result.prompt }))
          .catch(reason => send({ type: "shotmill:enhance-result", error: reason instanceof Error ? reason.message : "全局增强失败" }));
      } else if (message.type === "shotmill:import-file" && message.file instanceof File) {
        void gateway.importAsset(project.id, message.file, { name: message.file.name, category: "reference", tags: [] })
          .then(asset => { importedAssetIds.current.add(asset.id); send({ type: "shotmill:asset-result", asset: { id: asset.id, name: asset.name, kind: asset.mediaType, previewUrl: asset.previewUrl || asset.mediaUrl } }); void onRefresh(); })
          .catch(reason => send({ type: "shotmill:asset-result", error: reason instanceof Error ? reason.message : "导入素材失败" }));
      } else if (message.type === "shotmill:choose-files") {
        if (!onChooseLocalFiles) { send({ type: "shotmill:asset-result", error: "请使用上传资产选择文件" }); return; }
        void onChooseLocalFiles().then(async paths => {
          for (const path of paths) {
            const asset = await gateway.importLocalAsset(project.id, path, { name: path.split(/[\\/]/).at(-1) || path, category: "reference", tags: [] });
            importedAssetIds.current.add(asset.id);
            send({ type: "shotmill:asset-result", asset: { id: asset.id, name: asset.name, kind: asset.mediaType, previewUrl: asset.previewUrl || asset.mediaUrl } });
          }
          await onRefresh();
        }).catch(reason => send({ type: "shotmill:asset-result", error: reason instanceof Error ? reason.message : "选择素材失败" }));
      }
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [gateway, project, send, save, relink, onRefresh, onChooseLocalFiles, onSelection, onDirtyChange, onDuration, onToolbarChange, onGenerate, onClose, scheduleAutoSave]);

  return <div className="director-workspace-shell">
    {error && <div className="director-workspace-error" role="alert">{error}</div>}
    {saveError && <div className="director-save-error" role="alert"><span>工程保存失败：{saveError}</span><button type="button" onClick={() => { setSaveError(""); send({ type: "terrydirector:request-save" }); }}>重试保存</button></div>}
    <iframe ref={frame} title="TerryDirector 导演时间线" src="/director/index.html?embed=1&shotmill=1" />
    <Dialog open={!!importApproval} icon="delete" title="导入时间线" onClose={() => setImportApproval(null)}>
      <p>导入将替换当前 {project.snapshot.tasks.length} 个任务。原任务及其生成结果会被删除，无法恢复；本机原始素材不会删除。</p>
      <div className="task-lifecycle-actions">
        <Button onClick={() => setImportApproval(null)}>取消</Button>
        <Button variant="accent" onClick={() => {
          if (!importApproval) return;
          replacingTimeline.current = true;
          if (baseline.current) send({ type: "shotmill:import-result", document: importApproval });
          else pendingImportedDocument.current = importApproval;
          setImportApproval(null);
        }}>确认导入</Button>
      </div>
    </Dialog>
  </div>;
}
