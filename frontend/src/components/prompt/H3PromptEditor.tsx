import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";

import { OverlayPortal, useOverlayRegistration, useOverlayZIndex } from "../../ui/overlay";
import {
  findAssetMention,
  insertAssetReference,
  PromptAssetEditor,
  type AssetMention,
  type PromptAsset,
} from "./PromptAssetEditor";

export type H3PromptViewMode = "visual" | "text";

type H3PromptEditorProps = {
  value: string;
  onChange: (value: string) => void;
  assets: PromptAsset[];
  ariaLabel: string;
  viewMode: H3PromptViewMode;
  readOnly?: boolean;
};

const cameraLabels = new Map<string, string>([
  ["the camera pushes in", "推进"],
  ["the camera pulls out", "拉远"],
  ["the camera pans left", "左摇"],
  ["the camera pans right", "右摇"],
  ["the camera trucks left", "左移"],
  ["the camera trucks right", "右移"],
  ["the camera tilts up", "上摇"],
  ["the camera tilts down", "下摇"],
  ["the camera moves upward", "升镜"],
  ["the camera moves downward", "降镜"],
  ["the camera moves in an arc around the subject", "环绕"],
  ["the camera follows the moving subject in a tracking shot", "跟拍"],
  ["the camera holds a static shot", "固定镜头"],
  ["the camera zooms in", "变焦推近"],
  ["the camera zooms out", "变焦拉远"],
  ["the camera shakes slightly", "轻微晃动"],
  ["the camera shakes strongly", "强烈晃动"],
]);

const sectionLabels: Record<string, string> = {
  subject_definitions: "主体定义",
  summary: "摘要",
  retention_analysis: "保留关系分析",
  detailed_description: "详细描述",
  integrated_multimodal_description: "综合多模态描述",
  overall_soundscape: "整体声景",
  non_diegetic_music: "非剧情音乐",
};

const exactLabels: Record<string, string> = {
  fully_preserved: "完整保留",
  partially_preserved: "部分保留",
  attribute_transfer: "属性迁移",
  weak_reference: "弱参考",
  fully_copy: "完整复制",
  partially_copy: "部分复制",
  reference: "参考",
  "<scenetrans>": "跨镜头连续",
  "<cutoff>": "结尾截断",
  "[reference generation]": "参考生成",
  "[keyframe completion]": "关键帧补全",
  "[video editing]": "视频编辑",
  "[video continuation]": "视频续写",
  "[audio reuse]": "音频复用",
  "[audio reference]": "音频参考",
};

const H3_TOKEN_PATTERN = /<d>\[[^\]]+\][\s\S]*?<\/d>|<(?:Subject|Picture|Video|Audio)\s+\d+>|\[Shot\s+\d+\]|\(S\d+\)|<scenetrans>|<cutoff>|\b(?:fully_preserved|partially_preserved|attribute_transfer|weak_reference|fully_copy|partially_copy|reference)\b|\[\d{2}:\d{2}\]|^(?:subject_definitions|summary|retention_analysis|detailed_description|integrated_multimodal_description|overall_soundscape|non_diegetic_music):|\[(?:reference generation|keyframe completion|video editing|video continuation|audio reuse|audio reference)(?:\s*\+[^\]]+)?\]|The camera (?:pushes in|pulls out|pans left|pans right|trucks left|trucks right|tilts up|tilts down|moves upward|moves downward|moves in an arc around the subject|follows the moving subject in a tracking shot|holds a static shot|zooms in|zooms out|shakes slightly|shakes strongly)/gmi;

function tokenType(raw: string) {
  const value = raw.trim();
  if (/^(?:subject_definitions|summary|retention_analysis|detailed_description|integrated_multimodal_description|overall_soundscape|non_diegetic_music):$/i.test(value)) return "section";
  if (/^<Subject\s+\d+>$/i.test(value)) return "subject";
  if (/^<Picture\s+\d+>$/i.test(value)) return "picture";
  if (/^<Video\s+\d+>$/i.test(value)) return "video";
  if (/^<Audio\s+\d+>$/i.test(value)) return "audio";
  if (/^\[Shot\s+\d+\]$/i.test(value)) return "shot";
  if (/^\(S\d+\)$/i.test(value)) return "speaker";
  if (/^<d>\[/i.test(value)) return "dialogue";
  if (/^\[\d{2}:\d{2}\]$/.test(value)) return "time";
  if (/^<(scenetrans|cutoff)>$/i.test(value)) return "transition";
  if (/^\[(reference generation|keyframe completion|video editing|video continuation|audio reuse|audio reference)/i.test(value)) return "task";
  if (cameraLabels.has(value.toLowerCase())) return "camera";
  return "retention";
}

function visibleLabel(raw: string) {
  const value = raw.trim();
  const section = value.match(/^([a-z_]+):$/i);
  if (section && sectionLabels[section[1].toLowerCase()]) return sectionLabels[section[1].toLowerCase()];
  if (exactLabels[value.toLowerCase()]) return exactLabels[value.toLowerCase()];
  const camera = cameraLabels.get(value.toLowerCase());
  if (camera) return camera;
  let match = value.match(/^<Subject\s+(\d+)>$/i);
  if (match) return `主体 ${match[1]}`;
  match = value.match(/^<Picture\s+(\d+)>$/i);
  if (match) return `图片 ${match[1]}`;
  match = value.match(/^<Video\s+(\d+)>$/i);
  if (match) return `视频 ${match[1]}`;
  match = value.match(/^<Audio\s+(\d+)>$/i);
  if (match) return `音频 ${match[1]}`;
  match = value.match(/^\[Shot\s+(\d+)\]$/i);
  if (match) return `镜头 ${match[1]}`;
  match = value.match(/^\(S(\d+)\)$/i);
  if (match) return `说话人 S${match[1]}`;
  match = value.match(/^\[(\d{2}:\d{2})\]$/);
  if (match) return `时间 ${match[1]}`;
  return value;
}

function appendText(container: HTMLElement, text: string) {
  text.split("\n").forEach((part, index) => {
    if (index) container.append(document.createElement("br"));
    if (part) container.append(document.createTextNode(part));
  });
}

function mediaGlyph(asset: PromptAsset) {
  if (asset.kind === "subject") return "人";
  if (asset.kind === "video") return "▶";
  if (asset.kind === "audio") return "♪";
  return "图";
}

function createDialogueChip(raw: string, notifyChange: () => void, readOnly: boolean) {
  const match = raw.match(/^<d>\[([^\]]+)\]\s*([\s\S]*?)<\/d>$/i);
  const chip = document.createElement("span");
  chip.className = "h3-visual-chip is-dialogue";
  chip.contentEditable = "false";
  chip.dataset.raw = raw;
  if (!match) {
    chip.textContent = raw;
    return chip;
  }

  const language = document.createElement("select");
  language.className = "h3-dialogue-language";
  language.disabled = readOnly;
  language.setAttribute("aria-label", "对白语言");
  const languages = ["English", "Chinese", "Cantonese", "Japanese", "Korean", "Spanish", "French", "German", "Russian", "Other"];
  const current = match[1] || "English";
  for (const value of languages.includes(current) ? languages : [current, ...languages]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    option.selected = value === current;
    language.append(option);
  }

  const body = document.createElement("span");
  body.className = "h3-dialogue-text";
  body.contentEditable = String(!readOnly);
  body.spellcheck = false;
  body.textContent = match[2] || "";

  const update = () => {
    if (readOnly) return;
    const text = String(body.innerText || body.textContent || "").replace(/\r?\n/g, " ");
    chip.dataset.raw = `<d>[${language.value || "English"}] ${text}</d>`;
    notifyChange();
  };
  language.addEventListener("change", update);
  language.addEventListener("pointerdown", (event) => event.stopPropagation());
  body.addEventListener("input", update);
  body.addEventListener("pointerdown", (event) => event.stopPropagation());
  body.addEventListener("keydown", (event) => {
    if ((event.altKey && ["ArrowLeft", "ArrowRight"].includes(event.key))
      || ((event.ctrlKey || event.metaKey) && event.key === "Enter")) return;
    event.stopPropagation();
    if (event.key === "Enter") event.preventDefault();
  });
  chip.append(language, body);
  return chip;
}

function createTokenChip(raw: string, assets: PromptAsset[], notifyChange: () => void, readOnly: boolean) {
  const type = tokenType(raw);
  if (type === "dialogue") return createDialogueChip(raw, notifyChange, readOnly);

  const chip = document.createElement("span");
  chip.className = `h3-visual-chip is-${type}`;
  chip.contentEditable = "false";
  chip.dataset.raw = raw;

  const asset = assets.find((item) => item.reference.toLowerCase() === raw.trim().toLowerCase());
  if (asset) {
    chip.classList.add("is-media");
    if (!readOnly) { chip.setAttribute("role", "button"); chip.tabIndex = 0; chip.setAttribute("aria-label", `更换资产：${asset.name}`); }
    if (asset.previewUrl && asset.kind !== "audio") {
      const image = document.createElement("img");
      image.src = asset.previewUrl;
      image.alt = asset.name;
      chip.append(image);
    } else {
      const glyph = document.createElement("span");
      glyph.className = "h3-visual-chip-glyph";
      glyph.textContent = mediaGlyph(asset);
      chip.append(glyph);
    }
    const label = document.createElement("span");
    label.textContent = asset.name || visibleLabel(raw);
    chip.append(label);
    chip.title = `${visibleLabel(raw)} · ${asset.detail}`;
    return chip;
  }

  chip.textContent = visibleLabel(raw);
  chip.title = raw;
  return chip;
}

function serializeVisual(root: HTMLElement) {
  const visit = (node: Node): string => {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent || "";
    if (!(node instanceof HTMLElement)) return "";
    if (node.tagName === "BR") return "\n";
    if (node.dataset.raw != null) return node.dataset.raw;
    return Array.from(node.childNodes).map(visit).join("");
  };
  return Array.from(root.childNodes).map(visit).join("");
}

function serializedNodeLength(node: Node): number {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent?.length ?? 0;
  if (!(node instanceof HTMLElement)) return 0;
  if (node.tagName === "BR") return 1;
  if (node.dataset.raw != null) return node.dataset.raw.length;
  return Array.from(node.childNodes).reduce((sum, child) => sum + serializedNodeLength(child), 0);
}

function serializedCaretOffset(root: HTMLElement) {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0) return null;
  const range = selection.getRangeAt(0);
  const target = range.startContainer;
  const targetOffset = range.startOffset;
  if (target !== root && !root.contains(target)) return null;

  let total = 0;
  let found = false;
  const walk = (node: Node) => {
    if (found) return;
    if (node === target) {
      if (node.nodeType === Node.TEXT_NODE) {
        total += Math.min(targetOffset, node.textContent?.length ?? 0);
      } else if (node instanceof HTMLElement) {
        if (node.dataset.raw != null) {
          if (targetOffset > 0) total += node.dataset.raw.length;
        } else {
          const count = Math.min(targetOffset, node.childNodes.length);
          for (let index = 0; index < count; index += 1) total += serializedNodeLength(node.childNodes[index]);
        }
      }
      found = true;
      return;
    }

    if (node.nodeType === Node.TEXT_NODE) {
      total += serializedNodeLength(node);
      return;
    }
    if (node instanceof HTMLElement && (node.tagName === "BR" || node.dataset.raw != null)) {
      total += serializedNodeLength(node);
      return;
    }
    for (const child of Array.from(node.childNodes)) {
      walk(child);
      if (found) return;
    }
  };

  walk(root);
  return found ? total : null;
}

function placeSerializedCaret(root: HTMLElement, targetOffset: number) {
  const selection = window.getSelection();
  if (!selection) return;
  const range = document.createRange();
  let remaining = Math.max(0, targetOffset);
  let placed = false;

  const walk = (node: Node) => {
    if (placed) return;
    if (node.nodeType === Node.TEXT_NODE) {
      const length = node.textContent?.length ?? 0;
      if (remaining <= length) {
        range.setStart(node, remaining);
        placed = true;
      } else {
        remaining -= length;
      }
      return;
    }

    if (!(node instanceof HTMLElement)) return;
    const isAtomic = node.tagName === "BR" || node.dataset.raw != null;
    if (isAtomic) {
      const length = serializedNodeLength(node);
      if (remaining <= length) {
        const parent = node.parentNode;
        if (!parent) return;
        const index = Array.prototype.indexOf.call(parent.childNodes, node) as number;
        range.setStart(parent, index + (remaining > 0 ? 1 : 0));
        placed = true;
      } else {
        remaining -= length;
      }
      return;
    }

    for (const child of Array.from(node.childNodes)) {
      walk(child);
      if (placed) return;
    }
  };

  walk(root);
  if (!placed) {
    range.selectNodeContents(root);
    range.collapse(false);
  } else {
    range.collapse(true);
  }
  selection.removeAllRanges();
  selection.addRange(range);
  root.focus({ preventScroll: true });
}

function caretViewportPoint(root: HTMLElement) {
  const selection = window.getSelection();
  if (selection?.rangeCount) {
    const range = selection.getRangeAt(0).cloneRange();
    range.collapse(true);
    if (typeof range.getBoundingClientRect === "function") {
      const rect = range.getBoundingClientRect();
      if (rect.left || rect.top || rect.width || rect.height) return { left: rect.left, top: rect.bottom };
    }
  }
  const rect = root.getBoundingClientRect();
  return { left: rect.left + 14, top: rect.top + 44 };
}

function renderVisual(root: HTMLElement, value: string, assets: PromptAsset[], notifyChange: () => void, readOnly = false) {
  root.replaceChildren();
  H3_TOKEN_PATTERN.lastIndex = 0;
  let cursor = 0;
  for (const match of value.matchAll(H3_TOKEN_PATTERN)) {
    const index = match.index ?? 0;
    if (index > cursor) appendText(root, value.slice(cursor, index));
    root.append(createTokenChip(match[0], assets, notifyChange, readOnly));
    cursor = index + match[0].length;
  }
  if (cursor < value.length) appendText(root, value.slice(cursor));
  if (!value) root.append(document.createElement("br"));
}

export function H3PromptEditor({ value, onChange, assets, ariaLabel, viewMode, readOnly = false }: H3PromptEditorProps) {
  const visualRef = useRef<HTMLDivElement>(null);
  const renderedReadOnly = useRef<boolean | undefined>(undefined);
  const menuRef = useRef<HTMLDivElement>(null);
  const pendingDialogue = useRef(false);
  const [menuKind, setMenuKind] = useState<"asset" | "slash" | "replace">("asset");
  const pendingCaret = useRef<number | null>(null);
  const latestValue = useRef(value);
  const [mention, setMention] = useState<AssetMention | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [menuPosition, setMenuPosition] = useState({ left: 8, top: 8 });
  const menuId = useId();
  const menuOpen = !readOnly && viewMode === "visual" && mention !== null;
  const zIndex = useOverlayZIndex(30);
  latestValue.current = value;

  const assetKey = useMemo(() => assets.map((asset) => `${asset.id}:${asset.reference}:${asset.previewUrl || ""}:${asset.name}`).join("|"), [assets]);
  const visibleAssets = useMemo(() => {
    const options: PromptAsset[] = menuKind === "slash" ? [{ id: "dialogue", name: "对白块", kind: "subject", reference: "<d>[Chinese] </d>", detail: "dialogue · 可编辑对白", tone: "pink" }] : assets;
    if (!mention?.query) return options;
    return options.filter((asset) => `${asset.name} ${asset.reference} ${asset.detail} ${asset.kind}`
      .toLocaleLowerCase()
      .includes(mention.query));
  }, [assets, mention, menuKind]);

  const closeMenu = () => {
    setMention(null);
    setActiveIndex(0);
  };

  useOverlayRegistration(menuOpen, closeMenu);

  const updateMention = (root: HTMLElement, nextValue = serializeVisual(root)) => {
    if (readOnly) return;
    const caret = serializedCaretOffset(root);
    const slash = caret == null ? null : nextValue.slice(0, caret).match(/\/([^\/<>\n]*)$/);
    const nextMention = slash && caret != null ? { start: caret - slash[0].length, end: caret, query: slash[1].trim().toLowerCase() } : caret == null ? null : findAssetMention(nextValue, caret);
    setMenuKind(slash ? "slash" : "asset");
    setMention((current) => {
      if (!nextMention || !current || current.query !== nextMention.query || current.start !== nextMention.start) setActiveIndex(0);
      return nextMention;
    });
  };

  useLayoutEffect(() => {
    if (viewMode !== "visual") return;
    const root = visualRef.current;
    if (!root) return;
    const current = serializeVisual(root);
    if (current !== value || root.childNodes.length === 0 || renderedReadOnly.current !== readOnly) {
      renderedReadOnly.current = readOnly;
      renderVisual(root, value, assets, () => {
        const next = serializeVisual(root);
        latestValue.current = next;
        onChange(next);
      }, readOnly);
    }
    if (pendingCaret.current != null) {
      const caret = pendingCaret.current;
      pendingCaret.current = null;
      placeSerializedCaret(root, caret);
      if (pendingDialogue.current) {
        pendingDialogue.current = false;
        const selection = window.getSelection();
        const before = selection?.anchorNode === root ? root.childNodes[Math.max(0, (selection.anchorOffset || 1) - 1)] : selection?.anchorNode?.previousSibling;
        const body = before instanceof HTMLElement ? before.querySelector<HTMLElement>(".h3-dialogue-text") : null;
        if (body) { body.focus(); const range = document.createRange(); range.selectNodeContents(body); range.collapse(false); selection?.removeAllRanges(); selection?.addRange(range); }
      }
    }
  }, [assetKey, assets, onChange, value, viewMode, readOnly]);

  useEffect(() => {
    if (!menuOpen) return;
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (visualRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      closeMenu();
    };
    document.addEventListener("pointerdown", handlePointerDown, true);
    return () => document.removeEventListener("pointerdown", handlePointerDown, true);
  }, [menuOpen]);

  useLayoutEffect(() => {
    if (!menuOpen || !visualRef.current || !menuRef.current) return;
    const root = visualRef.current;
    const menu = menuRef.current;
    const place = () => {
      const point = caretViewportPoint(root);
      const width = menu.offsetWidth || 330;
      const height = Math.min(menu.offsetHeight || 300, window.innerHeight - 16);
      const maxLeft = Math.max(8, window.innerWidth - width - 8);
      const left = Math.min(Math.max(8, point.left), maxLeft);
      const below = point.top + 7;
      const top = below + height <= window.innerHeight - 8
        ? below
        : Math.max(8, point.top - height - 24);
      setMenuPosition({ left: Math.round(left), top: Math.round(top) });
    };
    place();
    root.addEventListener("scroll", place);
    window.addEventListener("resize", place);
    return () => {
      root.removeEventListener("scroll", place);
      window.removeEventListener("resize", place);
    };
  }, [mention?.end, mention?.query, menuOpen, visibleAssets.length]);

  useEffect(() => {
    setActiveIndex((current) => Math.min(current, Math.max(0, visibleAssets.length - 1)));
  }, [visibleAssets.length]);

  const chooseAsset = (asset: PromptAsset) => {
    const root = visualRef.current;
    if (!root || !mention) return;
    const current = serializeVisual(root);
    const result = menuKind === "replace" ? { value: current.slice(0, mention.start) + asset.reference + current.slice(mention.end), caret: mention.start + asset.reference.length } : insertAssetReference(current, mention, asset.reference);
    pendingDialogue.current = menuKind === "slash";
    pendingCaret.current = result.caret;
    latestValue.current = result.value;
    onChange(result.value);
    closeMenu();
  };

  if (viewMode === "text") {
    return <PromptAssetEditor value={value} onChange={onChange} assets={assets} ariaLabel={ariaLabel} rows={18} readOnly={readOnly} />;
  }

  return (
    <div className="h3-visual-editor-shell">
      <div
        ref={visualRef}
        className="h3-visual-editor"
        contentEditable={!readOnly}
        aria-readonly={readOnly}
        tabIndex={readOnly ? 0 : undefined}
        suppressContentEditableWarning
        role="textbox"
        aria-label={`${ariaLabel}可视化`}
        aria-multiline="true"
        aria-autocomplete="list"
        aria-controls={menuOpen ? menuId : undefined}
        aria-expanded={menuOpen}
        aria-haspopup="listbox"
        aria-activedescendant={menuOpen && visibleAssets[activeIndex] ? `${menuId}-${visibleAssets[activeIndex].id}` : undefined}
        data-placeholder="在这里编写 H3 提示词。标签、镜头、对白和素材引用会以可视化组件显示。"
        onInput={(event) => {
          if (readOnly) return;
          const next = serializeVisual(event.currentTarget);
          latestValue.current = next;
          onChange(next);
          updateMention(event.currentTarget, next);
        }}
        onClick={(event) => {
          const chip = (event.target as HTMLElement).closest<HTMLElement>(".is-media[data-raw]");
          if (!readOnly && chip && event.currentTarget.contains(chip)) {
            let start = 0;
            for (const node of Array.from(event.currentTarget.childNodes)) { if (node === chip) break; start += serializedNodeLength(node); }
            setMenuKind("replace"); setMention({ start, end: start + (chip.dataset.raw?.length || 0), query: "" }); setActiveIndex(0);
            return;
          }
          updateMention(event.currentTarget);
        }}
        onKeyUp={(event) => {
          // Escape dismisses the mention without changing its text or caret.
          // Re-reading that same caret on keyup would immediately reopen it.
          if (event.key === "Escape") return;
          if (["ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"].includes(event.key) && menuOpen) return;
          updateMention(event.currentTarget);
        }}
        onKeyDown={(event) => {
          if (!menuOpen && (event.key === "Enter" || event.key === " ") && (event.target as HTMLElement).matches('.is-media[role="button"]')) { event.preventDefault(); (event.target as HTMLElement).click(); return; }
          if (!menuOpen) return;
          if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            closeMenu();
            return;
          }
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            if (!visibleAssets.length) return;
            const delta = event.key === "ArrowDown" ? 1 : -1;
            setActiveIndex((current) => (current + delta + visibleAssets.length) % visibleAssets.length);
            return;
          }
          if ((event.key === "Enter" || event.key === "Tab") && visibleAssets[activeIndex]) {
            event.preventDefault();
            chooseAsset(visibleAssets[activeIndex]);
          }
        }}
        onBlur={(event) => {
          if (readOnly) return;
          const root = event.currentTarget;
          // Moving between the editor and its dialogue controls is not leaving it.
          // Rebuilding here would remove the control that is about to receive focus.
          if (event.relatedTarget instanceof Node && root.contains(event.relatedTarget)) return;
          const next = serializeVisual(root);
          if (next !== latestValue.current) onChange(next);
          renderVisual(root, next, assets, () => onChange(serializeVisual(root)));
          closeMenu();
        }}
      />
      {menuOpen && (
        <OverlayPortal>
          <div
            ref={menuRef}
            id={menuId}
            className="prompt-asset-menu sm-overlay-surface h3-visual-asset-menu"
            style={{ position: "fixed", ...menuPosition, ...zIndex }}
            role="listbox"
            aria-label={menuKind === "slash" ? "插入 H3 对白" : "引用任务资产"}
            data-testid="h3-visual-asset-menu"
          >
            <header><strong>{menuKind === "slash" ? "H3 语法" : menuKind === "replace" ? "更换资产" : "引用参考"}</strong><span>{mention.query ? `“${mention.query}”` : menuKind === "slash" ? "对白" : `${assets.length} 项资产`}</span></header>
            <div className="prompt-asset-options">
              {visibleAssets.map((asset, index) => (
                <button
                  key={`${asset.id}:${asset.reference}`}
                  id={`${menuId}-${asset.id}`}
                  type="button"
                  role="option"
                  aria-selected={index === activeIndex}
                  className={index === activeIndex ? "is-active" : ""}
                  onPointerMove={() => setActiveIndex(index)}
                  onPointerDown={(event) => event.preventDefault()}
                  onClick={() => chooseAsset(asset)}
                >
                  <span className={`prompt-asset-menu-thumb tone-${asset.tone}`}>
                    {asset.previewUrl && asset.kind !== "audio"
                      ? <img src={asset.previewUrl} alt="" />
                      : <span>{menuKind === "slash" ? "“ ”" : mediaGlyph(asset)}</span>}
                  </span>
                  <span className="prompt-asset-menu-copy"><strong>{asset.name}</strong><small>{menuKind === "slash" ? "可编辑对白" : `${asset.reference} · ${asset.detail}`}</small></span>
                  <kbd>↵</kbd>
                </button>
              ))}
              {!visibleAssets.length && <p className="prompt-asset-empty">没有匹配的任务资产。</p>}
            </div>
            <footer><span>↑↓ 选择</span><span>Enter / Tab 插入</span><span>Esc 关闭</span></footer>
          </div>
        </OverlayPortal>
      )}
    </div>
  );
}
