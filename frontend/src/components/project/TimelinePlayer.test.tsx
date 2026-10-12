import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import type { GenerationTask, Result } from "../../domain/storyboard";
import { TimelinePlayer } from "./TimelinePlayer";

afterEach(() => vi.restoreAllMocks());

it("preloads the next result and follows the director playhead across clips", async () => {
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (this: HTMLMediaElement) {
    Object.defineProperty(this, "paused", { configurable: true, value: false });
    return Promise.resolve();
  });
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (this: HTMLMediaElement) {
    Object.defineProperty(this, "paused", { configurable: true, value: true });
  });
  const tasks = [
    { id: "first", primaryResultId: "result-first", timelineStartSeconds: 0, plannedDurationSeconds: 1, storyboardFrame: {} },
    { id: "second", primaryResultId: "result-second", timelineStartSeconds: 1, plannedDurationSeconds: 1, storyboardFrame: {} },
  ] as GenerationTask[];
  const results = [
    { id: "result-first", videoUrl: "/first.mp4" },
    { id: "result-second", videoUrl: "/second.mp4" },
  ] as Result[];
  const onToggle = vi.fn();
  const view = render(<TimelinePlayer tasks={tasks} results={results} playback={{ frame: 0, playing: false, clipId: "first", clipStart: 0, clipEnd: 24 }} onToggle={onToggle} />);
  const first = view.container.querySelector('video[src="/first.mp4"]') as HTMLVideoElement;
  const second = view.container.querySelector('video[src="/second.mp4"]') as HTMLVideoElement;
  expect(first).toBeVisible();
  expect(second).toBeInTheDocument();
  for (const video of [first, second]) Object.defineProperty(video, "readyState", { value: HTMLMediaElement.HAVE_CURRENT_DATA });
  view.rerender(<TimelinePlayer tasks={tasks} results={results} playback={{ frame: 12, playing: true, clipId: "first", clipStart: 0, clipEnd: 24 }} onToggle={onToggle} />);
  expect(first.currentTime).toBeCloseTo(0.5);
  expect(play).toHaveBeenCalled();
  view.rerender(<TimelinePlayer tasks={tasks} results={results} playback={{ frame: 24, playing: true, clipId: "second", clipStart: 24, clipEnd: 48 }} onToggle={onToggle} />);
  expect(view.container.querySelector('video[src="/second.mp4"]')).toBe(second);
  expect(second).toHaveClass("is-active");
  expect(pause).toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "暂停时间线播放" }));
  expect(onToggle).toHaveBeenCalledOnce();
  expect(screen.getByRole("button", { name: "暂停时间线播放" }).querySelector("video")?.hasAttribute("controls")).toBe(false);
  view.unmount();
});
