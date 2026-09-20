import { X } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useId, useState } from "react";

import {
  OverlayDepth,
  OverlayPortal,
  useOverlayRegistration,
  useOverlayZIndex,
} from "./OverlaySystem";

type DialogProps = {
  open: boolean;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  onClose: () => void;
  size?: "default" | "wide";
};

export function Dialog({ open, title, description, children, onClose, size = "default" }: DialogProps) {
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
      <div className="sm-dialog-backdrop" data-state={open ? "open" : "closing"} aria-hidden={!open || undefined} inert={!open} style={backdropZ} onAnimationEnd={(event) => {
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
          >
            <header>
              <div>
                <h2 id={titleId}>{title}</h2>
                {description && <p>{description}</p>}
              </div>
              <button type="button" aria-label="关闭对话框" onClick={onClose}><X size={18} /></button>
            </header>
            <div className="sm-dialog-content">{children}</div>
          </section>
        </OverlayDepth>
      </div>
    </OverlayPortal>
  );
}
