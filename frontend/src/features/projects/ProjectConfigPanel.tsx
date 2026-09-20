import {
  FileImage,
  Folder,
  Info,
  Film,
  Maximize2,
  Music2,
  Trash2,
  Upload,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Checkbox, SegmentedControl, SlidingTabs, TextField } from "terry-react-ui-library";

import type { ProjectAsset } from "../../domain/storyboard";
import type { DirectorProject } from "../../mock/projects";
import { Dialog } from "../../ui/overlay";

type ProjectConfigTab = "info" | "assets";
type ProjectSettingsPatch = Pick<DirectorProject, "title" | "description" | "useDescriptionForAiPrompt">;

type Props = {
  open: boolean;
  project: DirectorProject;
  onClose: () => void;
  onSave: (settings: ProjectSettingsPatch, assets: ProjectAsset[]) => void;
};

const categoryLabel: Record<ProjectAsset["category"], string> = {
  character: "角色",
  scene: "场景",
  prop: "道具",
  reference: "参考",
};

const categories = Object.entries(categoryLabel) as Array<[ProjectAsset["category"], string]>;

function mediaLabel(asset: ProjectAsset) {
  if (asset.mediaType === "video") return "视频";
  if (asset.mediaType === "audio") return "音频";
  return "图片";
}

function assetFormat(asset: ProjectAsset) {
  const path = asset.projectRelativePath || "";
  const match = path.match(/\.([a-z0-9]+)(?:[?#].*)?$/i);
  return match?.[1]?.toUpperCase() || asset.mediaType.toUpperCase();
}

function originalFileName(asset: ProjectAsset) {
  if (asset.originalFilename) return asset.originalFilename;
  const normalized = (asset.projectRelativePath || "").replaceAll("\\", "/");
  return normalized.split("/").filter(Boolean).at(-1) || "—";
}

function mediaIcon(asset: ProjectAsset, size = 17) {
  if (asset.mediaType === "video") return <Film size={size} />;
  if (asset.mediaType === "audio") return <Music2 size={size} />;
  return <FileImage size={size} />;
}

function parseTags(value: string) {
  return value
    .split(/[，,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function AssetPreview({
  asset,
  onRename,
  onCategoryChange,
  onTagsChange,
}: {
  asset?: ProjectAsset;
  onRename: (name: string) => void;
  onCategoryChange: (category: ProjectAsset["category"]) => void;
  onTagsChange: (tags: string[]) => void;
}) {
  const previewRef = useRef<HTMLDivElement>(null);
  const [tagText, setTagText] = useState(asset?.tags.join("、") ?? "");

  useEffect(() => {
    setTagText(asset?.tags.join("、") ?? "");
  }, [asset?.id]);

  if (!asset) {
    return <div className="project-asset-preview-empty">选择左侧资产查看预览</div>;
  }

  const source = asset.previewUrl || asset.mediaUrl || asset.projectRelativePath;
  const requestFullscreen = () => {
    const target = previewRef.current;
    if (!target?.requestFullscreen) return;
    void target.requestFullscreen();
  };

  return (
    <div className="project-asset-detail">
      <div ref={previewRef} className={`project-asset-preview is-${asset.mediaType}`}>
        {asset.mediaType === "image" && source ? (
          <img src={source} alt={asset.name} />
        ) : asset.mediaType === "video" ? (
          <video controls preload="metadata" poster={asset.previewUrl} src={asset.mediaUrl || asset.projectRelativePath} />
        ) : asset.mediaType === "audio" ? (
          <div className="project-audio-preview">
            <Music2 size={38} />
            <strong>{asset.name}</strong>
            <audio controls preload="metadata" src={asset.mediaUrl || asset.projectRelativePath} />
          </div>
        ) : (
          <div className="project-asset-preview-empty">暂无预览</div>
        )}

        {asset.mediaType !== "audio" && (
          <button type="button" className="project-asset-fullscreen" aria-label="全屏查看资产" title="全屏查看" onClick={requestFullscreen}>
            <Maximize2 size={15} />
          </button>
        )}
      </div>

      <section className="project-asset-meta" aria-label="资产信息">
        <div className="project-asset-editable-meta">
          <label className="project-asset-name-field">
            <span>资产名</span>
            <TextField value={asset.name} onChange={onRename} placeholder="输入资产名" />
          </label>

          <div className="project-asset-category-field">
            <span>分类</span>
            <div className="project-asset-category-options">
              <SlidingTabs fluid ariaLabel="资产分类" value={asset.category} onChange={onCategoryChange} options={categories.map(([value, label]) => ({ value, label }))} />
            </div>
          </div>

          <label className="project-asset-tags-field">
            <span>标签</span>
            <TextField
              value={tagText}
              onChange={(value) => {
                setTagText(value);
                onTagsChange(parseTags(value));
              }}
              placeholder="例如：雨夜、主角、旧港口"
            />
          </label>
        </div>

        <div className="project-asset-readonly-title">文件信息</div>
        <dl className="project-asset-readonly-meta">
          <div><dt>格式</dt><dd>{assetFormat(asset)}</dd></div>
          <div><dt>类型</dt><dd>{mediaLabel(asset)}</dd></div>
          {typeof asset.durationSeconds === "number" && <div><dt>时长</dt><dd>{asset.durationSeconds.toFixed(1)} 秒</dd></div>}
          <div className="is-wide"><dt>原始文件名</dt><dd title={originalFileName(asset)}>{originalFileName(asset)}</dd></div>
        </dl>
      </section>
    </div>
  );
}

export function ProjectConfigPanel({ open, project, onClose, onSave }: Props) {
  const [tab, setTab] = useState<ProjectConfigTab>("info");
  const [title, setTitle] = useState(project.title);
  const [description, setDescription] = useState(project.description);
  const [useDescriptionForAiPrompt, setUseDescriptionForAiPrompt] = useState(project.useDescriptionForAiPrompt);
  const [assets, setAssets] = useState<ProjectAsset[]>(project.snapshot.assets);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(project.snapshot.assets[0]?.id ?? null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const nextAssets = project.snapshot.assets.map((asset) => ({ ...asset, tags: [...asset.tags] }));
    setTab("info");
    setTitle(project.title);
    setDescription(project.description);
    setUseDescriptionForAiPrompt(project.useDescriptionForAiPrompt);
    setAssets(nextAssets);
    setSelectedAssetId(nextAssets[0]?.id ?? null);
  }, [open, project]);

  const selectedAsset = useMemo(
    () => assets.find((asset) => asset.id === selectedAssetId) ?? assets[0],
    [assets, selectedAssetId],
  );

  useEffect(() => {
    if (!assets.length) {
      setSelectedAssetId(null);
      return;
    }
    if (!selectedAssetId || !assets.some((asset) => asset.id === selectedAssetId)) {
      setSelectedAssetId(assets[0].id);
    }
  }, [assets, selectedAssetId]);

  const importFiles = (files: FileList | null) => {
    if (!files?.length) return;
    const stamp = Date.now();
    const nextAssets = Array.from(files).map((file, index): ProjectAsset => {
      const mediaType: ProjectAsset["mediaType"] = file.type.startsWith("video/")
        ? "video"
        : file.type.startsWith("audio/")
          ? "audio"
          : "image";
      return {
        id: `asset-local-${stamp}-${index}`,
        name: file.name.replace(/\.[^.]+$/, "") || file.name,
        mediaType,
        category: "reference",
        projectRelativePath: file.name,
        previewUrl: mediaType === "image" || mediaType === "video" ? URL.createObjectURL(file) : undefined,
        tags: [],
        checksum: `local-${file.size}-${file.lastModified}`,
        originalFilename: file.name,
        sourceFile: file,
      };
    });
    setAssets((current) => [...current, ...nextAssets]);
    setSelectedAssetId(nextAssets[0]?.id ?? selectedAssetId);
  };

  const removeAsset = (assetId: string) => {
    setAssets((current) => current.filter((asset) => asset.id !== assetId));
  };

  const patchAsset = (assetId: string, patch: Partial<Pick<ProjectAsset, "name" | "category" | "tags">>) => {
    setAssets((current) => current.map((asset) => asset.id === assetId ? { ...asset, ...patch } : asset));
  };

  return (
    <Dialog open={open} size="wide" title="项目配置" onClose={onClose}>
      <div className="project-config-dialog project-config-dialog-v2">
        <nav className="project-config-tabs" aria-label="项目配置分类">
          <div className="project-config-tab-slot">
          <SegmentedControl fluid value={tab} onChange={setTab} ariaLabel="项目配置栏目" options={[
            { value: "info" as const, label: "项目信息", icon: <Info size={15} /> },
            { value: "assets" as const, label: "资产管理", icon: <Folder size={15} /> },
          ]} />
          </div>
        </nav>

        <section className="project-config-content">
          {tab === "info" ? (
            <div className="project-config-info">
              <label>
                <span>项目标题</span>
                <TextField value={title} onChange={setTitle} />
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
              <div className="project-context-checkbox">
                <Checkbox
                  checked={useDescriptionForAiPrompt}
                  onChange={setUseDescriptionForAiPrompt}
                  ariaLabel="AI 增强时使用项目简介作为背景"
                />
                <span>
                  <strong>AI 增强时使用项目简介作为背景</strong>
                </span>
              </div>
            </div>
          ) : (
            <div className="project-asset-manager-v2">
              <aside className="project-asset-browser" aria-label="项目资产列表">
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

                <div className="project-asset-list-v2">
                  {assets.map((asset) => (
                    <button
                      key={asset.id}
                      type="button"
                      className={`project-asset-row-v2 ${selectedAsset?.id === asset.id ? "is-selected" : ""}`}
                      onClick={() => setSelectedAssetId(asset.id)}
                    >
                      <span className="project-asset-thumb-v2" style={asset.previewUrl ? { backgroundImage: `url("${asset.previewUrl}")` } : undefined}>
                        {!asset.previewUrl && mediaIcon(asset)}
                      </span>
                      <span className="project-asset-copy-v2">
                        <strong>{asset.name}</strong>
                        <small>{categoryLabel[asset.category]} · {mediaLabel(asset)}</small>
                      </span>
                      <span
                        role="button"
                        tabIndex={0}
                        className="project-asset-remove-v2"
                        aria-label={`移除资产 ${asset.name}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          removeAsset(asset.id);
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            event.stopPropagation();
                            removeAsset(asset.id);
                          }
                        }}
                      ><Trash2 size={14} /></span>
                    </button>
                  ))}
                  {!assets.length && <div className="project-asset-empty-v2">项目还没有资产。</div>}
                </div>
              </aside>

              <main className="project-asset-inspector" aria-label="资产预览和信息">
                <AssetPreview
                  asset={selectedAsset}
                  onRename={(name) => selectedAsset && patchAsset(selectedAsset.id, { name })}
                  onCategoryChange={(category) => selectedAsset && patchAsset(selectedAsset.id, { category })}
                  onTagsChange={(tags) => selectedAsset && patchAsset(selectedAsset.id, { tags })}
                />
              </main>
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
            }, assets.map((asset) => ({ ...asset, name: asset.name.trim() || originalFileName(asset).replace(/\.[^.]+$/, "") || "未命名资产" })));
            onClose();
          }}>保存</Button>
        </footer>
      </div>
    </Dialog>
  );
}
