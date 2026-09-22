import { useEffect, useRef, useState } from "react";
import { Button } from "terry-react-ui-library";
import type { ComfyUIStatus } from "../../gateways/projectGateway";

export function BridgeStatus({ load, address }: { load: (signal?: AbortSignal) => Promise<ComfyUIStatus>; address?: string }) {
  const [status, setStatus] = useState<ComfyUIStatus>();
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(true);
  const retry = useRef<() => void>(() => {});
  useEffect(() => {
    let disposed = false;
    let active: AbortController | undefined;
    let poll: ReturnType<typeof setTimeout>;
    let deadline: ReturnType<typeof setTimeout>;
    setStatus(undefined); setError(""); setChecking(true);
    const check = async (manual = false) => {
      if (active) return;
      clearTimeout(poll);
      const controller = new AbortController(); active = controller;
      deadline = setTimeout(() => controller.abort(), 10000);
      if (manual) setChecking(true);
      try {
        const next = await load(controller.signal);
        if (!disposed) { setStatus(next); setError(""); }
      } catch {
        if (!disposed) { setStatus(undefined); setError("无法检查 Bridge，请确认应用后端可用后重试。"); }
      } finally {
        clearTimeout(deadline); active = undefined;
        if (!disposed) { setChecking(false); poll = setTimeout(() => void check(), 15000); }
      }
    };
    retry.current = () => void check(true);
    void check();
    return () => { disposed = true; clearTimeout(poll); clearTimeout(deadline); active?.abort(); };
  }, [load, address]);
  const ready = Boolean(status?.connected && status.bridgeNodeAvailable);
  const label = checking ? "Bridge 检查中…" : error ? "Bridge 状态未知" : ready ? "Bridge 已连接" : status?.bridgeState === "error" ? "Bridge 通信异常" : status?.connected ? "Bridge 未安装" : "Bridge 已断开";
  return <div className={`bridge-connection is-${ready ? "connected" : "disconnected"}`} role="status">
    <Button disabled={checking} onClick={() => retry.current()} title={error || status?.message} aria-label={label}><i className="bridge-connection-dot" />{label}</Button>
  </div>;
}
