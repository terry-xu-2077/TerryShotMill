import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { OverlayProvider } from "../../ui/overlay";
import { TaskReadOnlyDialog } from "./TaskReadOnlyDialog";

it("recovers failed reads without presenting editing controls", async () => {
  const api = {
    assets: vi.fn(),
    task: vi.fn().mockRejectedValueOnce(new Error("连接失败")).mockResolvedValue({ userPrompt: "保留提示词", aiEnhancedPrompt: "", promptSource: "user" }),
    results: vi.fn().mockResolvedValue([]),
  };
  render(<OverlayProvider><TaskReadOnlyDialog projectId="p" taskId="t" title="归档任务" gateway={api} onClose={vi.fn()} /></OverlayProvider>);
  expect(await screen.findByRole("alert")).toHaveTextContent("连接失败");
  await userEvent.click(screen.getByRole("button", { name: "重试" }));
  expect(await screen.findByText("此任务尚无生成结果。")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "任务内容" }));
  expect(screen.getByText("保留提示词")).toBeVisible();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /保存|生成视频|设为主结果/ })).not.toBeInTheDocument();
});
