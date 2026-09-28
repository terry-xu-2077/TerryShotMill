import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { ArchivedResult } from "../../gateways/resultArchiveGateway";
import type { ProjectSummary } from "../../gateways/projectGateway";
import { OverlayProvider } from "../../ui/overlay";
import { ArchiveImportDialog, ResultArchiveBrowser } from "./ResultArchiveBrowser";
import { ArchiveDeleteDialog } from "./ArchiveDeleteDialog";

const result: ArchivedResult = {
  id: "a", sourceProjectId: "p", sourceProjectTitle: "原项目", sourceTaskId: "t", sourceTaskTitle: "任务",
  generatedAt: "2026-09-27T00:00:00Z", archivedAt: "2026-09-27T00:01:00Z", finalPrompt: "原始提示词",
  params: {}, files: [{ role: "output", filename: "result.mp4", size: 10, url: "/api/v1/result-archive/a/files/0" }],
};

it("blocks duplicate deletion and dismissal while the request is pending", async () => {
  let finish!: () => void;
  const api = { list: vi.fn(), importInto: vi.fn(),
    delete: vi.fn(() => new Promise<void>(resolve => { finish = resolve; })) };
  const close = vi.fn();
  const deleted = vi.fn();
  render(<OverlayProvider><ArchiveDeleteDialog gateway={api} result={result}
    onClose={close} onDeleted={deleted} /></OverlayProvider>);
  const dialog = screen.getByRole("dialog", { name: "永久删除归档结果" });
  await userEvent.dblClick(within(dialog).getByRole("button", { name: "永久删除" }));
  expect(api.delete).toHaveBeenCalledTimes(1);
  expect(within(dialog).getByRole("button", { name: "取消" })).toBeDisabled();
  await userEvent.keyboard("{Escape}");
  await userEvent.click(within(dialog).getByRole("button", { name: "关闭对话框" }));
  expect(close).not.toHaveBeenCalled();
  expect(deleted).not.toHaveBeenCalled();
  await act(async () => finish());
  expect(deleted).toHaveBeenCalledExactlyOnceWith("a");
});

it("retries an archive listing failure and preserves project grouping", async () => {
  const api = { list: vi.fn().mockRejectedValueOnce(new Error("连接中断")).mockResolvedValue([result]), importInto: vi.fn(), delete: vi.fn() };
  render(<OverlayProvider><ResultArchiveBrowser gateway={api} projects={[]} onClose={vi.fn()} /></OverlayProvider>);
  expect(await screen.findByRole("alert")).toHaveTextContent("连接中断");
  await userEvent.click(screen.getByRole("button", { name: "重试" }));
  expect(await screen.findByRole("region", { name: "原项目 · 原项目" })).toHaveTextContent("任务");
  await userEvent.click(screen.getByRole("button", { name: "查看结果" }));
  expect(screen.getByRole("link", { name: "下载原文件" })).toHaveAttribute("href", "/api/v1/result-archive/a/files/0?download=true");
  await userEvent.click(screen.getByRole("button", { name: "生成信息" }));
  expect(screen.getByText("原始提示词")).toBeVisible();
});

it("imports only into writable projects and keeps selection for retry", async () => {
  const api = { list: vi.fn(), importInto: vi.fn().mockRejectedValueOnce(new Error("空间不足")).mockResolvedValue(undefined), delete: vi.fn() };
  const projects = [
    { id: "target", title: "目标" }, { id: "archive", title: "已归档目标", archivedAt: "date" },
    { id: "trash", title: "已删除目标", deletedAt: "date" },
  ] as ProjectSummary[];
  render(<OverlayProvider><ArchiveImportDialog gateway={api} result={result} projects={projects} onClose={vi.fn()} /></OverlayProvider>);
  expect(screen.queryByRole("button", { name: "已归档目标" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "已删除目标" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "导入" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "目标" }));
  await userEvent.click(screen.getByRole("button", { name: "导入" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("空间不足");
  expect(screen.getByRole("button", { name: "目标" })).toHaveAttribute("aria-pressed", "true");
  await userEvent.click(screen.getByRole("button", { name: "导入" }));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("已导入"));
  expect(api.importInto).toHaveBeenLastCalledWith("target", "a");
  expect(screen.queryByRole("button", { name: "导入" })).not.toBeInTheDocument();
});

it("confirms archive deletion, preserves failures, and removes only after success", async () => {
  const api = { list: vi.fn().mockResolvedValue([result]), importInto: vi.fn(),
    delete: vi.fn().mockRejectedValueOnce(new Error("删除失败")).mockResolvedValue(undefined) };
  render(<OverlayProvider><ResultArchiveBrowser gateway={api} projects={[]} onClose={vi.fn()} /></OverlayProvider>);
  await userEvent.click(await screen.findByRole("button", { name: "删除归档" }));
  expect(api.delete).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(api.delete).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "删除归档" }));
  await userEvent.click(screen.getByRole("button", { name: "永久删除" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("删除失败");
  expect(screen.getByRole("button", { name: "删除归档" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "永久删除" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "删除归档" })).not.toBeInTheDocument());
  expect(api.delete).toHaveBeenCalledTimes(2);
  expect(api.delete).toHaveBeenLastCalledWith("a");
  expect(api.list).toHaveBeenCalledTimes(1);
});
