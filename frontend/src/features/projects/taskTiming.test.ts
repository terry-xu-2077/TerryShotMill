import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { timingAt, useLiveTaskTimings } from "./taskTiming";

afterEach(() => vi.useRealTimers());

it("advances only live execution or queue measurements, and never invents unknown durations", () => {
  const measuredAt = "2026-09-21T00:00:00Z";
  const result = timingAt({ measuredAt, videoSeconds: 30, videoQueueSeconds: 8, videoRunning: false, promptSeconds: null, promptQueueSeconds: 12, promptQueued: true }, Date.parse(measuredAt) + 9000);
  expect(result.videoSeconds).toBe(30);
  expect(result.videoQueueSeconds).toBe(8);
  expect(result.promptSeconds).toBeNull();
  expect(result.promptQueueSeconds).toBe(21);
});

it("updates a running task each second then freezes when the server reports completion", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-21T00:00:00Z"));
  const { result, rerender } = renderHook(({ running }) => useLiveTaskTimings({
    task: { measuredAt: "2026-09-21T00:00:00Z", videoSeconds: 10, videoRunning: running },
  }), { initialProps: { running: true } });
  act(() => vi.advanceTimersByTime(3000));
  expect(result.current.task.videoSeconds).toBe(13);
  rerender({ running: false });
  act(() => vi.advanceTimersByTime(6000));
  expect(result.current.task.videoSeconds).toBe(10);
});
