import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { LifecycleGateway } from "../../gateways/lifecycleGateway";
import { OverlayProvider } from "../../ui/overlay";
import { TaskLifecycleDialog } from "./TaskLifecycleDialog";
import { TaskLifecycleBrowser } from "./TaskLifecycleBrowser";
import { TaskRiskSticker } from "./TaskRiskSticker";

function gateway(): LifecycleGateway {
  return {
    deletionPreview: vi.fn().mockResolvedValue([]),
    transitionTasks: vi.fn().mockResolvedValue([]),
    transitionProject: vi.fn(), listProjects: vi.fn(), getWorkspace: vi.fn(),
    purgeTasks: vi.fn().mockResolvedValue({ deletedIds: ["source"], archivedResultCount: 1, cleanupId: "c" }),
    purgeProject: vi.fn(),
  };
}

it("checks external impacts and confirms deletion in one dialog", async () => {
  const api = gateway();
  vi.mocked(api.deletionPreview).mockResolvedValue([{
    sourceTaskId: "source", sourceTaskTitle: "来源任务", targetTaskId: "next", targetTaskTitle: "后续任务",
    kind: "visual", sourceResultId: "result",
  }]);
  const close = vi.fn(); const changed = vi.fn().mockResolvedValue(undefined);
  render(<OverlayProvider><TaskLifecycleDialog projectId="p" gateway={api}
    intent={{ action: "trash", tasks: [{ id: "source", title: "来源任务" }] }}
    onClose={close} onChanged={changed} /></OverlayProvider>);
  expect(await screen.findByText(/后续任务：画面承接来源/)).toBeInTheDocument();
  expect(screen.getAllByRole("dialog")).toHaveLength(1);
  await userEvent.click(screen.getByRole("button", { name: "删除任务" }));
  expect(api.transitionTasks).toHaveBeenCalledWith("p", ["source"], "trash");
  expect(changed).toHaveBeenCalledOnce(); expect(close).toHaveBeenCalledOnce();
});

it("blocks deletion if impact checking fails and allows retry", async () => {
  const api = gateway();
  vi.mocked(api.deletionPreview).mockRejectedValueOnce(new Error("连接失败")).mockResolvedValue([]);
  render(<OverlayProvider><TaskLifecycleDialog projectId="p" gateway={api}
    intent={{ action: "trash", tasks: [{ id: "source", title: "来源任务" }] }}
    onClose={vi.fn()} onChanged={vi.fn()} /></OverlayProvider>);
  expect(await screen.findByRole("alert")).toHaveTextContent("连接失败");
  expect(screen.getByRole("button", { name: "删除任务" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "重试检查" }));
  await vi.waitFor(() => expect(screen.getByRole("button", { name: "删除任务" })).toBeEnabled());
});

it.each([true, false])("passes the explicit result retention choice (%s)", async retain => {
  const api = gateway();
  const close = vi.fn();
  render(<OverlayProvider><TaskLifecycleDialog projectId="p" gateway={api}
    intent={{ action: "purge", tasks: [{ id: "source", title: "来源任务" }] }}
    onClose={close} onChanged={vi.fn().mockResolvedValue(undefined)} /></OverlayProvider>);
  const checkbox = screen.getByRole("checkbox", { name: "归档全部生成结果后删除" });
  expect(checkbox).toBeChecked();
  if (!retain) await userEvent.click(checkbox);
  await vi.waitFor(() => expect(screen.getByRole("button", { name: "永久删除任务" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "永久删除任务" }));
  await waitFor(() => expect(close).toHaveBeenCalledOnce());
  expect(api.purgeTasks).toHaveBeenCalledWith("p", ["source"], retain);
});

it("does not repeat a committed destructive operation when refresh fails", async () => {
  const api = gateway();
  const changed = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(undefined);
  render(<OverlayProvider><TaskLifecycleDialog projectId="p" gateway={api}
    intent={{ action: "archive", tasks: [{ id: "source", title: "来源任务" }] }}
    onClose={vi.fn()} onChanged={changed} /></OverlayProvider>);
  await userEvent.click(screen.getByRole("button", { name: "归档任务" }));
  await userEvent.click(await screen.findByRole("button", { name: "重试刷新" }));
  expect(api.transitionTasks).toHaveBeenCalledOnce();
  expect(changed).toHaveBeenCalledTimes(2);
});

it("shows reference warnings on hover without a dialog", async () => {
  const user = userEvent.setup();
  render(<OverlayProvider><TaskRiskSticker tooltipOnly warnings={["承接来源已永久删除"]} /></OverlayProvider>);
  const button = screen.getByRole("button", { name: "查看引用警告" });
  await user.hover(button);
  expect(screen.getByRole("tooltip")).toHaveTextContent("承接来源已永久删除");
  await user.click(button);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
});

it("browses trash, restores a selection, and loads individual reference warnings", async () => {
  const api = gateway();
  vi.mocked(api.getWorkspace).mockResolvedValue({ project: { id: "p", title: "项目" },
    runtime: { state: "idle" }, tasks: [{
      id: "source", title: "来源任务", displayNumber: 1, promptExcerpt: "", status: "idle",
      assetCount: 0, resultCount: 0, durationSeconds: 6, generationSummary: { resolution: "", quality: "" },
    }],
  });
  render(<OverlayProvider><TaskLifecycleBrowser projectId="p" gateway={api} initialScope="trash"
    onClose={vi.fn()} onChanged={vi.fn().mockResolvedValue(undefined)} /></OverlayProvider>);
  await userEvent.click(await screen.findByRole("checkbox", { name: "选择任务 · 来源任务" }));
  await vi.waitFor(() => expect(api.deletionPreview).toHaveBeenCalledWith("p", ["source"]));
  await userEvent.click(screen.getByRole("button", { name: "恢复" }));
  const dialog = screen.getByRole("dialog", { name: "恢复任务" });
  await userEvent.click(within(dialog).getByRole("button", { name: "恢复任务" }));
  expect(api.transitionTasks).toHaveBeenCalledWith("p", ["source"], "restore");
});
