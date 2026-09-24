import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { OverlayProvider } from "../../ui/overlay";
import { BatchPromptDialog, BatchVideoDialog } from "./BatchReviewControls";

it("does not include previous-task context without explicit opt-in", async () => {
  const user = userEvent.setup();
  const onConfirm = vi.fn();
  render(<OverlayProvider><BatchPromptDialog open taskCount={2} eligibility={{ eligibleTaskIds: ["one", "two"], skipped: [] }} projectBackgroundAvailable={false} onClose={vi.fn()} onConfirm={onConfirm} /></OverlayProvider>);
  expect(screen.getByRole("checkbox", { name: "上一任务摘要" })).not.toBeChecked();
  await user.click(screen.getByRole("button", { name: "开始增强" }));
  expect(onConfirm).toHaveBeenCalledWith({ includeProjectBackground: false, includePreviousTaskSummary: false });
});

it("shows the effective model instead of a fixed model name", () => {
  render(<OverlayProvider><BatchPromptDialog open taskCount={2} projectBackgroundAvailable={false} aiLabel="API · selected-model" onClose={vi.fn()} /></OverlayProvider>);
  expect(screen.getByText("AI：API · selected-model")).toBeInTheDocument();
  expect(screen.queryByText("AI：Qwen3.8")).not.toBeInTheDocument();
});

it("explains provider rejection and prevents an empty submission", () => {
  render(<OverlayProvider><BatchVideoDialog open selectedCount={1} eligibility={{ eligibleTaskIds: [], skipped: [{ taskId: "task", reason: "invalid-params", code: "SHOTMILL_WORKFLOW_NOT_EXECUTABLE", message: "所选工作流无法执行，请检查工作流配置。" }] }} onClose={vi.fn()} onConfirm={vi.fn()} /></OverlayProvider>);
  expect(screen.getByText("所选工作流无法执行，请检查工作流配置。")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "生成 0 个视频" })).toBeDisabled();
});
