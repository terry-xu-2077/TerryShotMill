import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TaskPreview } from "./TaskPreview";

describe("task thumbnail duration", () => {
  it.each([false, true])("shows planned seconds with or without a cover, compact=%s", (compact) => {
    const view = render(<TaskPreview compact={compact} durationSeconds={15} />);
    expect(screen.getByText("15 秒")).toBeInTheDocument();
    view.rerender(<TaskPreview compact={compact} previewUrl="cover.jpg" durationSeconds={12.5} />);
    expect(screen.getByText("12.5 秒")).toBeInTheDocument();
    expect(screen.queryByText("15 秒")).toBeNull();
  });
  it.each([undefined, 0, -1, NaN])("does not invent a duration for %s", (durationSeconds) => {
    const { container } = render(<TaskPreview durationSeconds={durationSeconds} />);
    expect(container.querySelector(".task-preview-duration")).toBeNull();
  });
});
