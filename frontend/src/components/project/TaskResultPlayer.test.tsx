import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { TaskResultPlayer } from "./TaskResultPlayer";
afterEach(() => vi.restoreAllMocks());

it("preloads, advances without replacing the active surface, and obeys the continuous switch", () => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  const playlist = [0, 1, 2].map(i => ({ taskNumber: `T${i}`, result: { id: `r${i}`, jobId: `j${i}`, videoUrl: `/${i}.mp4`, metadata: {}, reviewState: "pending" as const } }));
  const onCurrentChange = vi.fn();
  const { container } = render(<TaskResultPlayer result={playlist[0].result} taskNumber="T0" playlist={playlist} onCurrentChange={onCurrentChange} onClose={() => {}} />);
  const [first, second] = container.querySelectorAll("video");
  const seek = vi.fn();
  Object.defineProperty(second, "currentTime", { configurable: true, get: () => 0, set: seek });
  const frameCallback = vi.fn();
  Object.defineProperty(second, "requestVideoFrameCallback", { configurable: true, value: frameCallback });
  expect(second).toHaveAttribute("src", "/1.mp4");
  fireEvent.ended(first);
  expect(first).toHaveClass("is-active");
  fireEvent.playing(second);
  expect(seek).not.toHaveBeenCalled();
  expect(frameCallback).not.toHaveBeenCalled();
  expect(second).toHaveClass("is-active");
  expect(first).toHaveAttribute("src", "/2.mp4");
  expect(onCurrentChange).toHaveBeenLastCalledWith(playlist[1]);
  fireEvent.click(screen.getByRole("button", { name: "ON" }));
  fireEvent.ended(second);
  expect(onCurrentChange).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "下一个视频" }));
  fireEvent.playing(first);
  expect(first).toHaveClass("is-active");
  expect(screen.getByRole("button", { name: "下一个视频" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "上一个视频" }));
  fireEvent.canPlay(second);
  fireEvent.playing(second);
  expect(onCurrentChange).toHaveBeenLastCalledWith(playlist[1]);
});

it("shows decoded media dimensions and duration without claiming planned values", () => {
  const onClose = vi.fn();
  const { container } = render(<TaskResultPlayer result={{ id: "r", jobId: "j",
    videoUrl: "/result.mp4", metadata: {}, reviewState: "pending" }} taskNumber="T01-004" onClose={onClose} />);
  expect(screen.queryByText(/864/)).not.toBeInTheDocument();
  const video = container.querySelector("video")!;
  expect(video.autoplay).toBe(true);
  expect(video.playsInline).toBe(true);
  Object.defineProperties(video, {
    videoWidth: { value: 864 }, videoHeight: { value: 480 }, duration: { value: 8 },
  });
  fireEvent.loadedMetadata(video);
  expect(screen.getByText("T01-004 · 864 × 480 · 8 秒")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  expect(onClose).toHaveBeenCalledOnce();
});
