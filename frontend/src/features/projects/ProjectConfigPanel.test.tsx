import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { makeMockProjects } from "../../mock/projects";
import { OverlayProvider } from "../../ui/overlay";
import { ProjectConfigPanel } from "./ProjectConfigPanel";

function renderPanel(onSave = vi.fn()) {
  const project = makeMockProjects()[0];
  return {
    project,
    onSave,
    ...render(
      <OverlayProvider>
        <ProjectConfigPanel open project={project} onClose={vi.fn()} onSave={onSave} />
      </OverlayProvider>,
    ),
  };
}

describe("ProjectConfigPanel", () => {
  it("uses a fixed two-column asset manager with an internal scroll list", async () => {
    const user = userEvent.setup();
    renderPanel();

    const dialog = screen.getByRole("dialog", { name: "项目配置" });
    await user.click(within(dialog).getByRole("button", { name: /资产管理/ }));

    expect(dialog.querySelector(".project-config-dialog-v2")).not.toBeNull();
    expect(within(dialog).getByRole("complementary", { name: "项目资产列表" })).toBeInTheDocument();
    expect(within(dialog).getByRole("main", { name: "资产预览和信息" })).toBeInTheDocument();
    expect(dialog.querySelector(".project-asset-list-v2")).not.toBeNull();
    expect(within(dialog).getByRole("button", { name: /添加资产/ })).toBeInTheDocument();
  });

  it("edits display metadata while keeping original filename readonly", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    renderPanel(onSave);

    const dialog = screen.getByRole("dialog", { name: "项目配置" });
    await user.click(within(dialog).getByRole("button", { name: /资产管理/ }));

    expect(within(dialog).getByText("linlan-rain.webp")).toBeInTheDocument();
    const nameInput = within(dialog).getByRole("textbox", { name: "资产名" });
    expect(nameInput).toHaveValue("林澜 · 雨夜造型");

    await user.clear(nameInput);
    await user.type(nameInput, "林澜雨夜主视觉");
    await user.click(within(dialog).getByRole("tab", { name: "道具" }));
    const tagsInput = within(dialog).getByRole("textbox", { name: "标签" });
    await user.clear(tagsInput);
    await user.type(tagsInput, "主视觉,雨夜");

    expect(within(dialog).getByText("林澜雨夜主视觉")).toBeInTheDocument();
    expect(within(dialog).getByText("linlan-rain.webp")).toBeInTheDocument();
    expect(within(dialog).getByRole("tablist", { name: "资产分类" })).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "保存" }));
    expect(onSave).toHaveBeenCalledTimes(1);
    const savedAssets = onSave.mock.calls[0][1];
    expect(savedAssets[0]).toMatchObject({
      name: "林澜雨夜主视觉",
      category: "prop",
      tags: ["主视觉", "雨夜"],
      projectRelativePath: "assets/characters/linlan-rain.webp",
    });
  });
});
