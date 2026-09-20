import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { TaskResultPlayer } from "./TaskResultPlayer";

it("shows decoded media dimensions and duration without claiming planned values", () => {
  const onClose = vi.fn();
  const { container } = render(<TaskResultPlayer result={{ id: "r", jobId: "j",
    videoUrl: "/result.mp4", metadata: {}, reviewState: "pending" }} taskNumber="T01-004" onClose={onClose} />);
  expect(screen.queryByText(/864/)).not.toBeInTheDocument();
  const video = container.querySelector("video")!;
  Object.defineProperties(video, {
    videoWidth: { value: 864 }, videoHeight: { value: 480 }, duration: { value: 8 },
  });
  fireEvent.loadedMetadata(video);
  expect(screen.getByText("T01-004 · 864 × 480 · 8 秒")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  expect(onClose).toHaveBeenCalledOnce();
});
