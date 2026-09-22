import { useEffect, useMemo, useState } from "react";
import type { TaskTiming } from "../../gateways/projectGateway";

export function formatElapsed(seconds?: number | null): string {
  if (seconds == null || !Number.isFinite(seconds)) return "暂无记录";
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total} 秒`;
  const minutes = Math.floor(total / 60);
  return minutes < 60 ? `${minutes} 分 ${total % 60} 秒` : `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`;
}

export function timingAt(timing: TaskTiming, now: number): TaskTiming {
  const measured = timing.measuredAt ? Date.parse(timing.measuredAt) : NaN;
  const extra = Number.isFinite(measured) ? Math.max(0, (now - measured) / 1000) : 0;
  const advance = (seconds: number | null | undefined, active?: boolean) => (
    seconds == null ? seconds : seconds + (active ? extra : 0)
  );
  return {
    ...timing,
    videoSeconds: advance(timing.videoSeconds, timing.videoRunning),
    videoQueueSeconds: advance(timing.videoQueueSeconds, timing.videoQueued),
    promptSeconds: advance(timing.promptSeconds, timing.promptRunning),
    promptQueueSeconds: advance(timing.promptQueueSeconds, timing.promptQueued),
  };
}

export function useLiveTaskTimings(timings?: Record<string, TaskTiming>) {
  const [now, setNow] = useState(Date.now);
  const running = Object.values(timings ?? {}).some((item) => item.videoRunning || item.videoQueued || item.promptRunning || item.promptQueued);
  useEffect(() => {
    setNow(Date.now());
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);
  return useMemo(() => Object.fromEntries(Object.entries(timings ?? {}).map(([id, value]) => [id, timingAt(value, now)])), [timings, now]);
}

export function taskTimeSummary(timing?: TaskTiming): string {
  if (!timing) return "";
  return [
    timing.promptSeconds != null ? `增强 ${formatElapsed(timing.promptSeconds)}` : timing.promptQueued ? `增强排队 ${formatElapsed(timing.promptQueueSeconds)}` : "",
    timing.videoSeconds != null ? `视频 ${formatElapsed(timing.videoSeconds)}` : timing.videoQueued ? `视频排队 ${formatElapsed(timing.videoQueueSeconds)}` : "",
  ].filter(Boolean).join(" · ");
}
