import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { OverlayProvider } from "../../ui/overlay";
import { ImportConfigurationDialog } from "./ImportConfigurationDialog";

function setup() {
  const gateway = {
    pending: vi.fn().mockResolvedValue([{ taskId: "t", title: "任务", revision: 4, sourceConfigurationId: "same" }]),
    options: vi.fn().mockResolvedValue([{ value: "same", label: "本机工作流" }]),
    confirm: vi.fn().mockResolvedValue(undefined),
  };
  render(<OverlayProvider><ImportConfigurationDialog projectId="p" gateway={gateway} onClose={vi.fn()} /></OverlayProvider>);
  return gateway;
}
async function choose() {
  await userEvent.click(await screen.findByRole("combobox"));
  await userEvent.click(screen.getByRole("option", { name: "本机工作流" }));
}
it("does not preselect matching names and explicitly confirms the task revision", async () => {
  const gateway = setup();
  expect(await screen.findByRole("button", { name: "确认配置" })).toBeDisabled();
  expect(screen.getByRole("combobox")).toHaveTextContent("选择本机工作流");
  await choose();
  await userEvent.click(screen.getByRole("button", { name: "确认配置" }));
  expect(await screen.findByRole("status")).toHaveTextContent("没有待确认的任务");
  expect(gateway.confirm).toHaveBeenCalledExactlyOnceWith("p", "t", "same", 4);
});
it("requires refresh after uncertain confirmation rather than resending", async () => {
  const gateway = setup();
  gateway.confirm.mockRejectedValueOnce(new Error("连接中断"));
  await choose();
  await userEvent.click(screen.getByRole("button", { name: "确认配置" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("刷新列表核对");
  expect(screen.queryByRole("button", { name: "确认配置" })).not.toBeInTheDocument();
  gateway.pending.mockResolvedValueOnce([]);
  await userEvent.click(screen.getByRole("button", { name: "刷新列表" }));
  expect(await screen.findByRole("status")).toHaveTextContent("没有待确认的任务");
  expect(gateway.confirm).toHaveBeenCalledOnce();
});
