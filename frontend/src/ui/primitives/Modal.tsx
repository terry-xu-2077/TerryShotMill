import { createContext, useContext, useLayoutEffect, useRef, useState, type ComponentProps } from "react";

const ModalPortalContext = createContext<HTMLDialogElement | null>(null);

export function useModalPortalTarget() {
  return useContext(ModalPortalContext);
}

export type ModalProps = Omit<ComponentProps<"dialog">, "open" | "onClose"> & {
  open: boolean;
  onDismiss: () => void;
};

const focusable = 'button, input:not([type="hidden"]), textarea, select, a[href], [tabindex], [contenteditable="true"], video[controls], audio[controls]';

function tabStops(host: HTMLDialogElement) {
  return Array.from(host.querySelectorAll<HTMLElement>(focusable)).filter(element =>
    element.tabIndex >= 0 && !element.matches(":disabled") && !element.closest("[inert]") &&
    element.getClientRects().length > 0 && getComputedStyle(element).visibility !== "hidden"
  );
}

/** Native modality owns background isolation and restoration; portals stay in its top layer. */
export function Modal({ open, onDismiss, children, className = "", onKeyDown, onCancel, ...props }: ModalProps) {
  const [host, setHost] = useState<HTMLDialogElement | null>(null);
  const wasOpen = useRef(false);
  const returnTarget = useRef<HTMLElement | null>(null);
  if (open && !wasOpen.current) {
    returnTarget.current = typeof document !== "undefined" && document.activeElement instanceof HTMLElement
      ? document.activeElement : null;
  }
  wasOpen.current = open;
  useLayoutEffect(() => {
    if (!host || !open) return;
    if (!host.open) host.showModal();
    const stops = tabStops(host);
    const initial = stops.find(element => element.hasAttribute("autofocus")) ??
      stops.find(element => element.matches('input, textarea, [contenteditable="true"]'));
    initial?.focus({ preventScroll: true });
    const previous = returnTarget.current;
    return () => {
      if (host.open) host.close();
      queueMicrotask(() => {
        if (!host.open && previous?.isConnected && !previous.closest("[inert], dialog:not([open])")) {
          previous.focus({ preventScroll: true });
        }
      });
    };
  }, [host, open]);

  return <dialog {...props} ref={setHost} role="presentation" className={`tc-modal-layer ${className}`.trim()}
    onCancel={event => {
      onCancel?.(event);
      if (event.defaultPrevented) return;
      event.preventDefault();
      onDismiss();
    }}
    onKeyDown={event => {
      onKeyDown?.(event);
      if (event.defaultPrevented || event.key !== "Tab" || !host ||
          (event.target as HTMLElement).closest("dialog[open]") !== host) return;
      const stops = tabStops(host);
      const first = stops[0];
      const last = stops.at(-1);
      if (!first || !last) { event.preventDefault(); host.focus(); return; }
      const active = document.activeElement;
      if (event.shiftKey && (active === first || active === host)) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (active === last || active === host)) {
        event.preventDefault(); first.focus();
      }
    }}>
    <ModalPortalContext.Provider value={host}>{children}</ModalPortalContext.Provider>
  </dialog>;
}
