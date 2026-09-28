import { useId, useRef, useState } from "react";
import { Dialog, OverlayPortal, useOverlayZIndex } from "../../ui/overlay";
import { useAnchoredPosition } from "../../ui/overlay/useAnchoredPosition";
import "./TaskRiskSticker.css";

export function TaskRiskSticker({ warnings, tooltipOnly = false }: { warnings: string[]; tooltipOnly?: boolean }) {
  const [open, setOpen] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const anchor = useRef<HTMLButtonElement>(null);
  const id = useId();
  const visible = tooltipOnly && (hovered || focused);
  const { surfaceRef, style } = useAnchoredPosition(anchor, visible, "down", 220);
  const layer = useOverlayZIndex(30);
  if (!warnings.length) return null;
  if (tooltipOnly) return <>
    <button ref={anchor} type="button" className="task-new-sticker task-risk-sticker"
      aria-label="查看引用警告" aria-describedby={visible ? id : undefined}
      onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
      onClick={event => event.stopPropagation()}
      onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); setHovered(false); setFocused(false); } }}>
      <span className="task-new-sticker-word">!</span>
    </button>
    {visible && <OverlayPortal><div ref={surfaceRef} id={id} role="tooltip"
      className="sm-overlay-surface task-reference-tooltip" style={{ ...style, ...layer }}>
      {warnings.map(warning => <p className="task-reference-message" key={warning}>{warning}</p>)}
    </div></OverlayPortal>}
  </>;
  return <>
    <button type="button" className="task-new-sticker task-risk-sticker" aria-label="查看任务生成风险"
      onClick={event => { event.stopPropagation(); setOpen(true); }}>
      <span className="task-new-sticker-word">!</span>
    </button>
    <Dialog open={open} icon="warning" title="生成风险" onClose={() => setOpen(false)}>
      <ul>{warnings.map(message => <li key={message}>{message}</li>)}</ul>
      <p>可以继续生成，提交前会再次列出这些风险。</p>
    </Dialog>
  </>;
}
