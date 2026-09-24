import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import type { ProjectWorkspaceView } from "../../gateways/projectGateway";
import { RuntimeCenter } from "./RuntimeCenter";

const runtime: ProjectWorkspaceView["runtime"] = {
  state: "idle",
  promptBatches: [{
    id: "batch1", createdAt: "2026-09-21T01:00:00Z", state: "running",
    completedCount: 1, failedCount: 1, cancelledCount: 0, queuedCount: 1, runningCount: 1,
    items: [
      { id: "1", taskId: "a", title: "码头", state: "completed", elapsedSeconds: 75 },
      { id: "2", taskId: "b", title: "雨夜", state: "failed", error: "增强服务不可用，请检查连接后重试。" },
      { id: "3", taskId: "c", title: "仓库", state: "queued" },
      { id: "4", taskId: "d", title: "港口", state: "running" },
    ],
  }],
  videoJobs: [{ id: "v1", taskId: "a", title: "码头视频", state: "running", elapsedSeconds: 18 }],
};

it("cancels only the displayed queued videos and leaves running work alone", async () => {
  const cancel = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(undefined);
  render(<RuntimeCenter runtime={{ ...runtime, videoJobs: [
    ...runtime.videoJobs!,
    { id: "v2", taskId: "b", title: "等待视频", state: "queued" },
    { id: "v3", taskId: "c", title: "已完成视频", state: "completed" },
  ] }} onCancel={vi.fn()} onRetry={vi.fn()} onCancelVideos={cancel} />);
  await userEvent.click(screen.getByRole("button", { name: "运行中心" }));
  const videos = within(screen.getByRole("region", { name: "视频生成记录" }));
  await userEvent.click(videos.getByRole("button", { name: "取消待执行视频" }));
  expect(cancel).toHaveBeenCalledExactlyOnceWith(["v2"]);
  expect(await screen.findByRole("alert")).toHaveTextContent("操作未确认");
  await userEvent.click(videos.getByRole("button", { name: "取消待执行视频" }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(videos.getByText("码头视频")).toBeInTheDocument();
});

it("opens persisted prompt and video history with counts, reasons and durations", async () => {
  render(<RuntimeCenter runtime={runtime} onCancel={vi.fn()} onRetry={vi.fn()} />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "运行中心" })).toHaveTextContent("失败 1");
  await userEvent.click(screen.getByRole("button", { name: "运行中心" }));
  const dialog = within(screen.getByRole("dialog", { name: "运行中心" }));
  expect(dialog.getByText("1 分 15 秒")).toBeInTheDocument();
  expect(dialog.getByText("码头视频")).toBeInTheDocument();
  expect(dialog.getByText("增强服务不可用，请检查连接后重试。")).toBeInTheDocument();
  expect(dialog.getByRole("button", { name: "取消待执行项" })).toBeInTheDocument();
});

it("waits for cancellation and retains a retryable failure in the open window", async () => {
  let reject!: (reason: Error) => void;
  const cancel = vi.fn().mockImplementationOnce(() => new Promise<void>((_, fail) => { reject = fail; })).mockResolvedValue(undefined);
  const retry = vi.fn().mockResolvedValue(undefined);
  render(<RuntimeCenter runtime={runtime} onCancel={cancel} onRetry={retry} />);
  await userEvent.click(screen.getByRole("button", { name: "运行中心" }));
  await userEvent.click(screen.getByRole("button", { name: "取消待执行项" }));
  expect(cancel).toHaveBeenCalledExactlyOnceWith("batch1");
  expect(screen.getByRole("button", { name: "重试失败项" })).toBeDisabled();
  reject(new Error("offline"));
  expect(await screen.findByRole("alert")).toHaveTextContent("操作未确认");
  await userEvent.click(screen.getByRole("button", { name: "取消待执行项" }));
  await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "重试失败项" }));
  expect(retry).toHaveBeenCalledExactlyOnceWith("batch1");
  expect(screen.getByRole("dialog", { name: "运行中心" })).toBeInTheDocument();
});


it("distinguishes a waiting continuation from explicit fallback consent", async () => {
  const action = vi.fn().mockResolvedValue(undefined);
  render(<RuntimeCenter projects={[{ project: { id: "p", title: "电影" }, runtime: {
    state: "queued", videoJobs: [
      { id: "waiting", taskId: "a", title: "第二段", state: "queued", statusNote: "等待上一任务结果" },
      { id: "fallback", taskId: "b", title: "第三段", state: "queued", paused: true,
        continuationFallback: true, error: "上一任务失败，继续将不承接。" },
    ],
  } }]} onTaskAction={action} />);
  await userEvent.click(screen.getByRole("button", { name: "运行中心" }));
  expect(screen.getByText("等待上一任务结果")).toBeInTheDocument();
  expect(screen.getByText("承接异常 · 待确认")).toBeInTheDocument();
  expect(action).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "继续生成（不承接） 第三段" }));
  expect(action).toHaveBeenCalledWith("p", "video", "fallback", "resume");
});
