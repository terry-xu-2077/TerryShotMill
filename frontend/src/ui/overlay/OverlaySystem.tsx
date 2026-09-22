import {
  createContext,
  type CSSProperties,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { useModalPortalTarget } from "terry-react-ui-library";

type OverlayRegistration = {
  id: string;
  close: () => void;
};

type ToastItem = {
  id: number;
  message: string;
  tone: "normal" | "success" | "danger";
};

type OverlayContextValue = {
  register: (registration: OverlayRegistration) => () => void;
  pushToast: (message: string, tone?: ToastItem["tone"]) => void;
};

const OverlayContext = createContext<OverlayContextValue | null>(null);
const OverlayDepthContext = createContext(0);

function overlayRoot(): HTMLElement {
  const root = document.getElementById("shotmill-overlay-root");
  if (!root) throw new Error("ShotMill overlay root is missing.");
  return root;
}

export function OverlayProvider({ children }: { children: ReactNode }) {
  const stack = useRef<OverlayRegistration[]>([]);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const toastSequence = useRef(0);
  const toastTimers = useRef<Set<number>>(new Set());

  const register = useCallback((registration: OverlayRegistration) => {
    stack.current = [...stack.current.filter((item) => item.id !== registration.id), registration];
    return () => {
      stack.current = stack.current.filter((item) => item.id !== registration.id);
    };
  }, []);

  const pushToast = useCallback((message: string, tone: ToastItem["tone"] = "normal") => {
    const id = ++toastSequence.current;
    setToasts((current) => [...current, { id, message, tone }]);
    const timer = window.setTimeout(() => {
      toastTimers.current.delete(timer);
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, 2600);
    toastTimers.current.add(timer);
  }, []);

  useEffect(() => () => {
    toastTimers.current.forEach((timer) => window.clearTimeout(timer));
    toastTimers.current.clear();
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      const top = stack.current.at(-1);
      if (!top) return;
      event.preventDefault();
      event.stopPropagation();
      top.close();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const value = useMemo(() => ({ register, pushToast }), [pushToast, register]);

  return (
    <OverlayContext.Provider value={value}>
      {children}
      {createPortal(
        <div className="sm-toast-viewport" aria-live="polite" aria-label="通知">
          {toasts.map((toast) => (
            <div key={toast.id} className={`sm-toast tone-${toast.tone}`} role="status">
              {toast.message}
            </div>
          ))}
        </div>,
        overlayRoot(),
      )}
    </OverlayContext.Provider>
  );
}

export function OverlayPortal({ children }: { children: ReactNode }) {
  const modalTarget = useModalPortalTarget();
  return createPortal(children, modalTarget ?? overlayRoot());
}

export function OverlayDepth({ children }: { children: ReactNode }) {
  const parentDepth = useContext(OverlayDepthContext);
  return <OverlayDepthContext.Provider value={parentDepth + 1}>{children}</OverlayDepthContext.Provider>;
}

export function useOverlayZIndex(offset = 0): CSSProperties {
  const depth = useContext(OverlayDepthContext);
  return { zIndex: 400 + depth * 100 + offset };
}

export function useOverlayRegistration(open: boolean, onClose: () => void) {
  const context = useContext(OverlayContext);
  const id = useId();
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!open || !context) return;
    return context.register({ id, close: () => closeRef.current() });
  }, [context, id, open]);
}

export function useToast() {
  const context = useContext(OverlayContext);
  if (!context) throw new Error("useToast must be used inside OverlayProvider.");
  return context.pushToast;
}
