import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { LifecycleGateway } from "../../gateways/lifecycleGateway";
import { OverlayProvider } from "../../ui/overlay";
import { TaskLifecycleDialog } from "./TaskLifecycleDialog";
import { TaskRiskSticker } from "./TaskRiskSticker";

function gateway(): LifecycleGateway {
  return {
    deletionPreview: vi.fn().mockResolvedValue([]),
    listProjects: vi.fn(), getWorkspace: vi.fn(),
    deleteTasks: vi.fn().mockResolvedValue({ deletedIds: ["source"] }),
    removeProject: vi.fn(),
  };
}
const intent = { tasks: [{ id: "source", title: "来源任务" }] };

it("checks dependent tasks and permanently deletes directly after confirmation", async () => {
  const api = gateway();
  vi.mocked(api.deletionPreview).mockResolvedValue([{
    sourceTaskId: "source", sourceTaskTitle: "来源任务", targetTaskId: "next", targetTaskTitle: "后续任务",
    kind: "visual", sourceResultId: "result",
  }]);
  const close = vi.fn(); const changed = vi.fn().mockResolvedValue(undefined);
  render(<OverlayProvider><TaskLifecycleDialog projectId="p" gateway={api} intent={intent}
    onClose={close} onChanged={changed} /></OverlayProvider>);
  expect(await screen.findByText(/后续任务：画面承接来源/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "确认删除" }));
  expect(api.deleteTasks).toHaveBeenCalledWith("p", ["source"]);
  expect(changed).toHaveBeenCalledOnce(); expect(close).toHaveBeenCalledOnce();
});

it("blocks deletion if impact checking fails and allows retry", async () => {
  const api = gateway();
  vi.mocked(api.deletionPreview).mockRejectedValueOnce(new Error("连接失败")).mockResolvedValue([]);
  render(<OverlayProvider><TaskLifecycleDialog projectId="p" gateway={api} intent={intent}
    onClose={vi.fn()} onChanged={vi.fn()} /></OverlayProvider>);
  expect(await screen.findByRole("alert")).toHaveTextContent("连接失败");
  expect(screen.getByRole("button", { name: "确认删除" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "重试检查" }));
  await vi.waitFor(() => expect(screen.getByRole("button", { name: "确认删除" })).toBeEnabled());
});

it("does not repeat deletion when refresh fails", async () => {
  const api = gateway();
  const changed = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(undefined);
  render(<OverlayProvider><TaskLifecycleDialog projectId="p" gateway={api} intent={intent}
    onClose={vi.fn()} onChanged={changed} /></OverlayProvider>);
  await userEvent.click(await screen.findByRole("button", { name: "确认删除" }));
  await userEvent.click(await screen.findByRole("button", { name: "重试刷新" }));
  expect(api.deleteTasks).toHaveBeenCalledOnce();
  expect(changed).toHaveBeenCalledTimes(2);
});

it("shows reference warnings on hover without a dialog", async () => {
  const user = userEvent.setup();
  render(<OverlayProvider><TaskRiskSticker tooltipOnly warnings={["承接来源已删除"]} /></OverlayProvider>);
  const button = screen.getByRole("button", { name: "查看引用警告" });
  await user.hover(button);
  expect(screen.getByRole("tooltip")).toHaveTextContent("承接来源已删除");
  await user.click(button);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
});
