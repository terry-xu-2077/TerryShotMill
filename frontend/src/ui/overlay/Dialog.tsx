import { X, PanelsTopLeft, Settings, SlidersHorizontal, FolderPlus, Pencil, Sparkles,
  Film, Images, Image, Camera, Clapperboard, FileText, History, TriangleAlert,
  Activity, Trash2, Save, Replace } from "lucide-react";
import type { KeyboardEventHandler, ReactNode } from "react";
import { useEffect, useId, useState } from "react";
import { Modal } from "terry-react-ui-library";

import {
  OverlayDepth,
  OverlayPortal,
  useOverlayRegistration,
  useOverlayZIndex,
} from "./OverlaySystem";

const titleIcons = {
  window: PanelsTopLeft, settings: Settings, configure: SlidersHorizontal, create: FolderPlus,
  edit: Pencil, enhance: Sparkles, video: Film, assets: Images, image: Image, camera: Camera,
  task: Clapperboard, script: FileText, history: History, warning: TriangleAlert,
  runtime: Activity, delete: Trash2, save: Save, replace: Replace,
};

type DialogProps = {
  icon?: keyof typeof titleIcons;
  open: boolean;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  onClose: () => void;
  size?: "default" | "wide";
  onKeyDown?: KeyboardEventHandler<HTMLElement>;
};

export function Dialog({ open, title, description, children, onClose, size = "default", onKeyDown, icon = "window" }: DialogProps) {
  const TitleIcon = titleIcons[icon];
  const titleId = useId();
  const [present, setPresent] = useState(open);
  useEffect(() => {
    if (open) { setPresent(true); return; }
    const timer = window.setTimeout(() => setPresent(false), 200);
    return () => window.clearTimeout(timer);
  }, [open]);
  useOverlayRegistration(open, onClose);
  const backdropZ = useOverlayZIndex(50);
  const dialogZ = useOverlayZIndex(60);

  if (!open && !present) return null;

  return (
    <OverlayPortal>
      <Modal open={open} onDismiss={onClose} className="sm-dialog-backdrop" data-state={open ? "open" : "closing"} aria-hidden={!open || undefined} inert={!open} style={backdropZ} onAnimationEnd={(event) => {
        if (!open && event.target === event.currentTarget) setPresent(false);
      }} onMouseDown={(event) => {
        if (open && event.currentTarget === event.target) onClose();
      }}>
        <OverlayDepth>
          <section
            className={`sm-dialog size-${size}`}
            style={dialogZ}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            onKeyDown={onKeyDown}
          >
            <header>
              <div>
                <h2 id={titleId} className="sm-dialog-title"><TitleIcon className="sm-dialog-title-icon" size={18} strokeWidth={1.7} aria-hidden="true" /><span className="sm-dialog-title-content">{title}</span></h2>
                {description && <p>{description}</p>}
              </div>
              <button type="button" aria-label="关闭对话框" onClick={onClose}><X size={18} /></button>
            </header>
            <div className="sm-dialog-content">{children}</div>
          </section>
        </OverlayDepth>
      </Modal>
    </OverlayPortal>
  );
}
