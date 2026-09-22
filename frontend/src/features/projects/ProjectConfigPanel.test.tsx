import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { makeMockProjects } from "../../mock/projects";
import { OverlayProvider } from "../../ui/overlay";
import { ProjectConfigPanel } from "./ProjectConfigPanel";

function renderPanel(onSave = vi.fn(), onClose = vi.fn()) {
  const project = makeMockProjects()[0];
  return {
    project,
    onSave,
    onClose,
    ...render(
      <OverlayProvider>
        <ProjectConfigPanel open project={project} onClose={onClose} onSave={onSave} />
      </OverlayProvider>,
    ),
  };
}

describe("ProjectConfigPanel", () => {
  it("waits for saving, prevents duplicate submissions and preserves edits on failure", async () => {
    const user = userEvent.setup();
    let rejectSave!: (error: Error) => void;
    const onSave = vi.fn().mockImplementationOnce(() => new Promise<void>((_resolve, reject) => { rejectSave = reject; })).mockResolvedValue(undefined);
    const { onClose } = renderPanel(onSave);
    const title = screen.getByRole("textbox", { name: "项目标题" });
    await user.clear(title);
    await user.type(title, "保留我的修改");
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "保存中…" })).toBeDisabled();
    rejectSave(new Error("offline"));
    expect(await screen.findByRole("alert")).toHaveTextContent("保存失败");
    expect(title).toHaveValue("保留我的修改");
    expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(onSave.mock.calls[1]).toEqual(onSave.mock.calls[0]);
  });

  it("opens an asset image directly and closes it by clicking the large image", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /资产管理/ }));
    expect(screen.queryByRole("button", { name: "全屏查看资产" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("img", { name: "林澜 · 雨夜造型" }));
    const preview = screen.getByRole("dialog", { name: "林澜 · 雨夜造型" });
    await user.click(within(preview).getByRole("img", { name: "林澜 · 雨夜造型" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "林澜 · 雨夜造型" })).not.toBeInTheDocument());
    expect(screen.getByRole("dialog", { name: "项目配置" })).toBeInTheDocument();
  });
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
