import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { OverlayProvider } from "../../ui/overlay";
import { BatchPromptDialog } from "./BatchReviewControls";

it("does not include previous-task context without explicit opt-in", async () => {
  const user = userEvent.setup();
  const onConfirm = vi.fn();
  render(<OverlayProvider><BatchPromptDialog open taskCount={2} projectBackgroundAvailable={false} onClose={vi.fn()} onConfirm={onConfirm} /></OverlayProvider>);
  expect(screen.getByRole("checkbox", { name: "上一任务摘要" })).not.toBeChecked();
  await user.click(screen.getByRole("button", { name: "开始增强" }));
  expect(onConfirm).toHaveBeenCalledWith({ includeProjectBackground: false, includePreviousTaskSummary: false });
});
