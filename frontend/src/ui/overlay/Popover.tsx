import type { ReactNode } from "react";
import { useEffect, useId, useRef, useState } from "react";

import { OverlayPortal, useOverlayRegistration, useOverlayZIndex } from "./OverlaySystem";
import { useAnchoredPosition } from "./useAnchoredPosition";

type PopoverProps = {
  label: string;
  trigger: ReactNode;
  children: ReactNode | ((close: () => void) => ReactNode);
  className?: string;
  triggerClassName?: string;
  triggerLabel?: string;
};

export function Popover({ label, trigger, children, className = "", triggerClassName = "", triggerLabel }: PopoverProps) {
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLButtonElement>(null);
  const id = useId();
  const { surfaceRef, placement, style } = useAnchoredPosition(anchorRef, open, "down", 260);
  const zIndex = useOverlayZIndex(25);
  const closeAndRestore = () => { setOpen(false); anchorRef.current?.focus({ preventScroll: true }); };
  useOverlayRegistration(open, closeAndRestore);

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => {
      const first = surfaceRef.current?.querySelector<HTMLElement>('button:not(:disabled), input:not(:disabled), [tabindex="0"]');
      (first ?? surfaceRef.current)?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [open, surfaceRef]);

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      const target = event.target as Node;
      if (anchorRef.current?.contains(target) || surfaceRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("pointerdown", close, true);
    return () => document.removeEventListener("pointerdown", close, true);
  }, [open, surfaceRef]);

  return (
    <>
      <button ref={anchorRef} className={`sm-inline-trigger ${triggerClassName}`.trim()} type="button"
        aria-label={triggerLabel} aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? id : undefined}
        onClick={() => setOpen((value) => !value)}>
        {trigger}
      </button>
      {open && (
        <OverlayPortal>
          <div
            ref={surfaceRef}
            className={`sm-popover sm-overlay-surface ${className}`.trim()}
            id={id}
            tabIndex={-1}
            style={{ ...style, ...zIndex }}
            role="dialog"
            aria-label={label}
            data-placement={placement}
            onBlur={event => {
              if (!event.currentTarget.contains(event.relatedTarget as Node | null) && event.relatedTarget !== anchorRef.current) setOpen(false);
            }}
          >
            {typeof children === "function" ? children(closeAndRestore) : children}
          </div>
        </OverlayPortal>
      )}
    </>
  );
}
