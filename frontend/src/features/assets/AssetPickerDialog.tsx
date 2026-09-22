import { Check, FileImage, Film, Music2, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "terry-react-ui-library";

import type { AssetCategory, AssetMediaType, ProjectAsset, TaskAssetBinding } from "../../domain/storyboard";
import { Dialog, PortalSelect } from "../../ui/overlay";

function bindingRole(asset: ProjectAsset): TaskAssetBinding["role"] {
  if (asset.mediaType === "audio") return "audio";
  if (asset.category === "character") return "character";
  if (asset.category === "scene") return "scene";
  if (asset.category === "prop") return "prop";
  return "reference";
}

function mediaLabel(type: AssetMediaType) {
  if (type === "video") return "视频";
  if (type === "audio") return "音频";
  return "图片";
}

function categoryLabel(category: AssetCategory) {
  if (category === "character") return "角色";
  if (category === "scene") return "场景";
  if (category === "prop") return "道具";
  return "参考";
}

function AssetIcon({ type }: { type: AssetMediaType }) {
  if (type === "video") return <Film size={22} />;
  if (type === "audio") return <Music2 size={22} />;
  return <FileImage size={22} />;
}

type AssetPickerDialogProps = {
  open: boolean;
  assets: ProjectAsset[];
  initialBindings: TaskAssetBinding[];
  onClose: () => void;
  onConfirm: (bindings: TaskAssetBinding[]) => void;
};

export function AssetPickerDialog({ open, assets, initialBindings, onClose, onConfirm }: AssetPickerDialogProps) {
  const [query, setQuery] = useState("");
  const [mediaType, setMediaType] = useState<"all" | AssetMediaType>("all");
  const [category, setCategory] = useState<"all" | AssetCategory>("all");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [previewId, setPreviewId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setSelectedIds(initialBindings.map((binding) => binding.assetId));
    setPreviewId(initialBindings[0]?.assetId ?? assets[0]?.id ?? null);
    setQuery("");
    setMediaType("all");
    setCategory("all");
  }, [assets, initialBindings, open]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return assets.filter((asset) =>
      (mediaType === "all" || asset.mediaType === mediaType)
      && (category === "all" || asset.category === category)
      && (!needle || [asset.name, asset.mediaType, asset.category, ...asset.tags].join(" ").toLocaleLowerCase().includes(needle)),
    );
  }, [assets, category, mediaType, query]);
  const preview = assets.find((asset) => asset.id === previewId) ?? filtered[0];

  return (
    <Dialog open={open} size="wide" icon="assets" title="选择分镜素材" description="选择角色、场景、道具或参考素材；只有确认后才会应用到当前分镜。" onClose={onClose}>
      <div className="asset-picker-dialog">
        <section className="asset-picker-browser">
          <header>
            <label className="asset-search"><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称或标签" aria-label="搜索素材" /></label>
            <PortalSelect value={mediaType} onChange={(value) => setMediaType(value as typeof mediaType)} ariaLabel="素材媒体类型" options={[
              { value: "all", label: "全部媒体" }, { value: "image", label: "图片" }, { value: "video", label: "视频" }, { value: "audio", label: "音频" },
            ]} />
            <PortalSelect value={category} onChange={(value) => setCategory(value as typeof category)} ariaLabel="素材分类" options={[
              { value: "all", label: "全部分类" }, { value: "character", label: "角色" }, { value: "scene", label: "场景" }, { value: "prop", label: "道具" }, { value: "reference", label: "参考" },
            ]} />
          </header>
          <div className="asset-picker-grid" role="listbox" aria-label="项目素材" aria-multiselectable="true">
            {filtered.map((asset) => {
              const selected = selectedIds.includes(asset.id);
              return (
                <article key={asset.id} className={selected ? "is-selected" : ""} role="option" aria-selected={selected} aria-label={`${asset.name} ${mediaLabel(asset.mediaType)} ${categoryLabel(asset.category)}`}>
                  <button type="button" className="asset-picker-thumb" onClick={() => setPreviewId(asset.id)} aria-label={`预览 ${asset.name}`} style={asset.previewUrl ? { backgroundImage: `url("${asset.previewUrl}")` } : undefined}>
                    <AssetIcon type={asset.mediaType} />
                    <span>{mediaLabel(asset.mediaType)}</span>
                  </button>
                  <button type="button" className="asset-picker-select" onClick={() => setSelectedIds((current) => selected ? current.filter((id) => id !== asset.id) : [...current, asset.id])}>
                    <span><strong>{asset.name}</strong><small>{categoryLabel(asset.category)} · {asset.tags.join(" · ")}</small></span>
                    {selected && <Check size={15} />}
                  </button>
                </article>
              );
            })}
          </div>
          {filtered.length === 0 && <p className="asset-picker-empty">没有匹配的素材。</p>}
        </section>
        <aside className="asset-picker-preview" aria-label="素材预览">
          {preview ? (
            <>
              <div style={preview.previewUrl ? { backgroundImage: `url("${preview.previewUrl}")` } : undefined}><AssetIcon type={preview.mediaType} /></div>
              <span>{mediaLabel(preview.mediaType)} · {categoryLabel(preview.category)}</span>
              <h3>{preview.name}</h3>
              <p>{preview.projectRelativePath}</p>
              <small>{preview.tags.map((tag) => <em key={tag}>{tag}</em>)}</small>
            </>
          ) : <p>选择一个素材查看详情。</p>}
        </aside>
        <footer>
          <span>已选择 {selectedIds.length} 项</span>
          <Button onClick={onClose}>取消</Button>
          <Button variant="accent" onClick={() => onConfirm(selectedIds.map((assetId) => {
            const asset = assets.find((item) => item.id === assetId)!;
            return { assetId, role: bindingRole(asset) };
          }))}>添加到分镜</Button>
        </footer>
      </div>
    </Dialog>
  );
}
