import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { ProjectCoverEditor } from "./ProjectCoverEditor";

it("does not offer frame capture before the video has a decoded frame", async () => {
  render(<ProjectCoverEditor assets={[]} results={[{ id: "result", jobId: "j", videoUrl: "/clip.mp4", metadata: {}, reviewState: "pending" }]} custom={false} onChange={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "从视频截取" }));
  expect(screen.getByRole("button", { name: "使用当前画面" })).toBeDisabled();
  const video = document.querySelector("video")!;
  Object.defineProperties(video, { readyState: { value: 2 }, videoWidth: { value: 640 }, videoHeight: { value: 360 } });
  fireEvent.loadedData(video);
  expect(screen.getByRole("button", { name: "使用当前画面" })).toBeEnabled();
});
