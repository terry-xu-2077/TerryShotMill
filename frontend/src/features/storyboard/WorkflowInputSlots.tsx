import { FileImage, Film, Music2, RefreshCw, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button, TextField } from "terry-react-ui-library";
import type { ProjectAsset, TaskAssetBinding } from "../../domain/storyboard";
import type { ComfyUIWorkflow, WorkflowInputSelection } from "../../gateways/projectGateway";
import { Dialog } from "../../ui/overlay";
import "./WorkflowInputSlots.css";

type Props = {
  open: boolean;
  workflowFile?: string;
  bindings: TaskAssetBinding[];
  assets: ProjectAsset[];
  loadWorkflows?: () => Promise<ComfyUIWorkflow[]>;
  value?: WorkflowInputSelection | null;
  onChange: (value: WorkflowInputSelection, bindings: TaskAssetBinding[]) => void;
};

function workflowKey(file: string) {
  const normalized = file.replaceAll("\\", "/");
  const marker = normalized.toLowerCase().lastIndexOf("/workflows/");
  return marker >= 0 ? normalized.slice(marker + 11) : normalized;
}

function AssetThumbnail({ asset }: { asset: ProjectAsset }) {
  const [failed, setFailed] = useState(false);
  const Icon = asset.mediaType === "audio" ? Music2 : asset.mediaType === "video" ? Film : FileImage;
  if (!failed && asset.previewUrl && asset.mediaType !== "audio") {
    return <img className="workflow-slot-thumbnail" src={asset.previewUrl} alt={asset.name} onError={() => setFailed(true)} />;
  }
  if (!failed && asset.mediaType === "video" && asset.mediaUrl) {
    return <video className="workflow-slot-thumbnail" src={asset.mediaUrl} muted playsInline preload="metadata" aria-label={asset.name} onError={() => setFailed(true)} />;
  }
  return <Icon size={22} aria-hidden="true" />;
}

export function WorkflowInputSlots({ open, workflowFile, bindings, assets, loadWorkflows, value, onChange }: Props) {
  const loader = useRef(loadWorkflows);
  loader.current = loadWorkflows;
  const [catalog, setCatalog] = useState<ComfyUIWorkflow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [editingPort, setEditingPort] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  useEffect(() => {
    if (!open || !workflowFile || !loader.current) return;
    let active = true;
    setCatalog([]);
    setLoading(true);
    setError(false);
    void loader.current().then((items) => { if (active) setCatalog(items); })
      .catch(() => { if (active) setError(true); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, workflowFile, attempt]);

  const key = workflowKey(workflowFile ?? "");
  const workflow = catalog.find((item) => item.relativePath === key || item.id === key);
  const ports = workflow?.inputs.filter((port) => !["STRING", "TEXT", "INT", "FLOAT", "BOOLEAN"].includes(port.type.toUpperCase())) ?? [];
  const assetsById = new Map(assets.map((asset) => [asset.id, asset]));
  const types: Record<string, string> = { IMAGE: "图片", VIDEO: "视频", AUDIO: "音频", MASK: "遮罩" };
  const counters: Record<string, number> = {};
  const descriptors = ports.map((port, index) => {
    const type = port.type.toUpperCase();
    const number = counters[type] = (counters[type] ?? 0) + 1;
    const portId = `${port.targetNodeId ?? ""}:${port.targetPort || port.portName || port.name}:${port.sourceNodeId ?? ""}`;
    const saved = value?.workflowId === key ? value.slots.find((slot) => slot.portId === portId) : undefined;
    const legacy = !value ? bindings[index] : undefined;
    return { port, type, portId, label: `${types[type] ?? "输入"} ${number}`, assetId: saved?.assetId ?? legacy?.assetId ?? null,
      reference: saved?.reference ?? legacy?.reference ?? `<${type === "VIDEO" ? "Video" : type === "AUDIO" ? "Audio" : "Picture"} ${number}>` };
  });
  const activePort = descriptors.find((port) => port.portId === editingPort);
  const assign = (portId: string, assetId: string | null) => {
    const slots = descriptors.map((slot) => ({ portId: slot.portId, reference: slot.reference, assetId: slot.portId === portId ? assetId : slot.assetId }));
    onChange({ workflowId: key, slots }, slots.flatMap((slot): TaskAssetBinding[] => {
      const asset = slot.assetId ? assetsById.get(slot.assetId) : undefined;
      const previous = bindings.find((binding) => binding.assetId === slot.assetId && binding.reference === slot.reference);
      return asset ? [{ ...previous, assetId: asset.id, role: previous?.role ?? (asset.mediaType === "audio" ? "audio" : asset.category), reference: slot.reference }] : [];
    }));
    setEditingPort(null);
  };
  const availableAssets = assets.filter((asset) => activePort && (activePort.type === "*" || activePort.type === asset.mediaType.toUpperCase()) && asset.name.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  return <section className="workflow-input-slots" aria-label="工作流输入资产" aria-busy={loading}>
    <header className="workflow-input-slots-heading">
      <strong>输入资产</strong>
      {workflow && <span>{bindings.length} 项资产 · {ports.length} 个槽位</span>}
    </header>
    {!workflowFile ? <p className="workflow-input-slots-message">未配置生成工作流</p>
      : loading ? <p className="workflow-input-slots-message" role="status">正在读取工作流输入槽位…</p>
        : error ? <div className="workflow-input-slots-message" role="alert">无法读取输入槽位<Button size="icon" aria-label="重试读取输入槽位" onClick={() => setAttempt((value) => value + 1)}><RefreshCw size={16} /></Button></div>
          : !workflow ? <p className="workflow-input-slots-message">工作流槽位信息不可用</p>
            : ports.length === 0 ? <p className="workflow-input-slots-message">此工作流没有媒体输入槽位</p>
              : <ul className="workflow-input-slot-list" aria-label="媒体输入槽位">
                {descriptors.map(({ port, type, portId, label, assetId }) => {
                  const asset = assetId ? assetsById.get(assetId) : undefined;
                  const mismatch = asset && type !== "*" && type !== asset.mediaType.toUpperCase();
                  const Icon = type === "AUDIO" ? Music2 : type === "VIDEO" ? Film : FileImage;
                  const target = port.portName || port.targetPort || port.name;
                  return <li className="workflow-input-slot-item" key={portId}><button type="button" className={`workflow-input-slot${asset ? " is-filled" : ""}${mismatch ? " is-invalid" : ""}`} aria-label={`${label} · ${target} · ${asset?.name ?? (assetId ? "资产不可用" : "空槽位（可选）")}${mismatch ? " · 类型不匹配" : ""}`} onClick={() => { setEditingPort(portId); setQuery(""); }}>
                    <div className="workflow-input-slot-media">{asset ? <AssetThumbnail key={asset.id} asset={asset} /> : <Icon size={22} aria-hidden="true" />}</div>
                    <strong className="workflow-input-slot-label">{label}</strong>
                    <span className="workflow-input-slot-target" title={target}>{target.split(".").at(-1)}</span>
                    <span className="workflow-input-slot-name" title={asset?.name}>{mismatch ? "类型不匹配" : asset?.name ?? (assetId ? "资产不可用" : "可选")}</span>
                  </button></li>;
                })}
              </ul>}
    {workflow && !value && bindings.length > ports.length && <p className="workflow-input-slots-warning" role="alert">有 {bindings.length - ports.length} 项资产超出当前工作流槽位。</p>}
    <Dialog open={Boolean(activePort) && open} title={`选择资产 · ${activePort?.label ?? ""}`} onClose={() => setEditingPort(null)}>
      <div className="workflow-slot-picker">
        <label className="workflow-slot-search">搜索资产<TextField placeholder="搜索项目资产" value={query} onChange={setQuery} /></label>
        <div className="workflow-slot-picker-assets" role="group" aria-label="可填入的项目资产">
          {availableAssets.map((asset) => <button type="button" className="workflow-slot-picker-asset" key={asset.id} onClick={() => activePort && assign(activePort.portId, asset.id)} aria-label={`填入 ${asset.name}`}>
            <div className="workflow-input-slot-media"><AssetThumbnail asset={asset} /></div><span>{asset.name}</span>
          </button>)}
          {availableAssets.length === 0 && <p>没有匹配的项目资产</p>}
        </div>
        <footer className="workflow-slot-picker-footer"><Button disabled={!activePort?.assetId} onClick={() => activePort && assign(activePort.portId, null)}><X size={14} />清空槽位</Button><Button onClick={() => setEditingPort(null)}>取消</Button></footer>
      </div>
    </Dialog>
  </section>;
}
