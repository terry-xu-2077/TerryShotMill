import { FileImage, Film, UserRound, Volume2 } from "lucide-react";
import {
  type ChangeEvent,
  type KeyboardEvent,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { OverlayPortal, useOverlayRegistration, useOverlayZIndex } from "../ui/overlay";

export type PromptAssetKind = "subject" | "picture" | "video" | "audio";

export type PromptAsset = {
  id: string;
  name: string;
  kind: PromptAssetKind;
  reference: string;
  detail: string;
  tone: string;
  previewUrl?: string;
};

export type AssetMention = {
  start: number;
  end: number;
  query: string;
};

const kindMeta = {
  subject: { label: "主体", icon: UserRound },
  picture: { label: "图片", icon: FileImage },
  video: { label: "视频", icon: Film },
  audio: { label: "音频", icon: Volume2 },
} satisfies Record<PromptAssetKind, { label: string; icon: typeof FileImage }>;

export function findAssetMention(value: string, caret: number): AssetMention | null {
  const beforeCaret = value.slice(0, caret);
  const match = beforeCaret.match(/@([^@\n]*)$/);
  if (!match || match.index == null) return null;
  return {
    start: match.index,
    end: caret,
    query: match[1].trim().toLocaleLowerCase(),
  };
}

export function insertAssetReference(value: string, mention: AssetMention, reference: string) {
  const suffix = value.slice(mention.end);
  const separator = suffix.length > 0 && /^\s/.test(suffix) ? "" : " ";
  const nextValue = `${value.slice(0, mention.start)}${reference}${separator}${suffix}`;
  return {
    value: nextValue,
    caret: mention.start + reference.length + separator.length,
  };
}

function caretPoint(textarea: HTMLTextAreaElement) {
  const rect = textarea.getBoundingClientRect();
  if (!rect.width || !rect.height) return { left: rect.left, top: rect.bottom };

  const computed = window.getComputedStyle(textarea);
  const mirror = document.createElement("div");
  const marker = document.createElement("span");
  const properties = [
    "borderBottomWidth", "borderLeftWidth", "borderRightWidth", "borderTopWidth",
    "boxSizing", "fontFamily", "fontSize", "fontStyle", "fontWeight", "letterSpacing",
    "lineHeight", "paddingBottom", "paddingLeft", "paddingRight", "paddingTop",
    "textAlign", "textIndent", "textTransform", "wordSpacing",
  ] as const;

  for (const property of properties) mirror.style[property] = computed[property];
  Object.assign(mirror.style, {
    position: "fixed",
    left: `${rect.left}px`,
    top: `${rect.top}px`,
    width: `${rect.width}px`,
    height: `${rect.height}px`,
    overflow: "hidden",
    overflowWrap: "break-word",
    pointerEvents: "none",
    visibility: "hidden",
    whiteSpace: "pre-wrap",
  });
  mirror.textContent = textarea.value.slice(0, textarea.selectionStart);
  marker.textContent = "\u200b";
  mirror.append(marker);
  document.body.append(mirror);
  mirror.scrollTop = textarea.scrollTop;
  mirror.scrollLeft = textarea.scrollLeft;
  const markerRect = marker.getBoundingClientRect();
  mirror.remove();

  if (!markerRect.height) return { left: rect.left + 12, top: rect.bottom };
  return { left: markerRect.left, top: markerRect.bottom };
}

type PromptAssetEditorProps = {
  value: string;
  onChange: (value: string) => void;
  assets: PromptAsset[];
  ariaLabel: string;
  rows?: number;
  readOnly?: boolean;
};

export function PromptAssetEditor({ value, onChange, assets, ariaLabel, rows = 10, readOnly = false }: PromptAssetEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const pendingCaret = useRef<number | null>(null);
  const dismissedMention = useRef<{ value: string; caret: number } | null>(null);
  const [mention, setMention] = useState<AssetMention | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [menuPosition, setMenuPosition] = useState({ left: 8, top: 8 });
  const menuId = useId();
  const zIndex = useOverlayZIndex(30);
  const open = !readOnly && mention !== null;

  const visibleAssets = useMemo(() => {
    if (!mention?.query) return assets;
    return assets.filter((asset) => {
      const meta = kindMeta[asset.kind];
      return `${asset.name} ${asset.reference} ${asset.detail} ${meta.label}`
        .toLocaleLowerCase()
        .includes(mention.query);
    });
  }, [assets, mention]);

  const closeMenu = () => {
    const textarea = textareaRef.current;
    if (textarea) dismissedMention.current = { value: textarea.value, caret: textarea.selectionStart };
    setMention(null);
    setActiveIndex(0);
  };

  useOverlayRegistration(open, closeMenu);

  useEffect(() => {
    if (pendingCaret.current == null) return;
    const caret = pendingCaret.current;
    pendingCaret.current = null;
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.focus({ preventScroll: true });
    textarea.setSelectionRange(caret, caret);
  }, [value]);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (textareaRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      closeMenu();
    };
    document.addEventListener("pointerdown", handlePointerDown, true);
    return () => document.removeEventListener("pointerdown", handlePointerDown, true);
  }, [open]);

  useLayoutEffect(() => {
    if (!open || !textareaRef.current || !menuRef.current) return;
    const textarea = textareaRef.current;
    const menu = menuRef.current;
    const place = () => {
      const point = caretPoint(textarea);
      const width = menu.offsetWidth || 320;
      const height = Math.min(menu.offsetHeight || 280, window.innerHeight - 16);
      const maxLeft = Math.max(8, window.innerWidth - width - 8);
      const left = Math.min(Math.max(8, point.left), maxLeft);
      const below = point.top + 7;
      const top = below + height <= window.innerHeight - 8
        ? below
        : Math.max(8, point.top - height - 24);
      setMenuPosition({ left: Math.round(left), top: Math.round(top) });
    };
    place();
    textarea.addEventListener("scroll", place);
    window.addEventListener("resize", place);
    return () => {
      textarea.removeEventListener("scroll", place);
      window.removeEventListener("resize", place);
    };
  }, [mention?.end, mention?.query, open, visibleAssets.length]);

  useEffect(() => {
    setActiveIndex((current) => Math.min(current, Math.max(0, visibleAssets.length - 1)));
  }, [visibleAssets.length]);

  const updateMention = (nextValue: string, caret: number) => {
    if (readOnly) return;
    // A selection event from the same keypress must not reopen a dismissed menu.
    if (dismissedMention.current?.value === nextValue && dismissedMention.current.caret === caret) return;
    dismissedMention.current = null;
    const nextMention = findAssetMention(nextValue, caret);
    setMention(nextMention);
    if (!mention || nextMention?.query !== mention.query) setActiveIndex(0);
  };

  const handleChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    if (readOnly) return;
    const nextValue = event.target.value;
    dismissedMention.current = null;
    onChange(nextValue);
    updateMention(nextValue, event.target.selectionStart);
  };

  const chooseAsset = (asset: PromptAsset) => {
    if (!mention) return;
    const result = insertAssetReference(value, mention, asset.reference);
    pendingCaret.current = result.caret;
    onChange(result.value);
    closeMenu();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (!open) return;
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
  };

  return (
    <div className="prompt-asset-editor">
      <textarea
        ref={textareaRef}
        value={value}
        readOnly={readOnly}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onClick={(event) => updateMention(value, event.currentTarget.selectionStart)}
        onSelect={(event) => {
          if (open) updateMention(value, event.currentTarget.selectionStart);
        }}
        aria-label={ariaLabel}
        aria-autocomplete="list"
        aria-controls={open ? menuId : undefined}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-activedescendant={open && visibleAssets[activeIndex] ? `${menuId}-${visibleAssets[activeIndex].id}` : undefined}
        rows={rows}
      />
      {!readOnly && <div className="prompt-asset-hint"><span>@</span> 输入 @ 引用当前任务资产</div>}
      {open && (
        <OverlayPortal>
          <div
            ref={menuRef}
            id={menuId}
            className="prompt-asset-menu sm-overlay-surface"
            style={{ position: "fixed", ...menuPosition, ...zIndex }}
            role="listbox"
            aria-label="引用任务资产"
            data-testid="prompt-asset-menu"
          >
            <header><strong>引用参考</strong><span>{mention.query ? `“${mention.query}”` : `${assets.length} 项资产`}</span></header>
            <div className="prompt-asset-options">
              {visibleAssets.map((asset, index) => {
                const meta = kindMeta[asset.kind];
                const Icon = meta.icon;
                return (
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
                    <span className={`prompt-asset-menu-thumb tone-${asset.tone}`}><Icon size={17} /></span>
                    <span className="prompt-asset-menu-copy"><strong>{asset.name}</strong><small>{asset.reference} · {meta.label} · {asset.detail}</small></span>
                    <kbd>↵</kbd>
                  </button>
                );
              })}
              {!visibleAssets.length && <p className="prompt-asset-empty">没有匹配的任务资产。</p>}
            </div>
            <footer><span>↑↓ 选择</span><span>Enter / Tab 插入</span><span>Esc 关闭</span></footer>
          </div>
        </OverlayPortal>
      )}
    </div>
  );
}
