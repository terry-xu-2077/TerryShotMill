import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { makeMockProjects } from "../../mock/projects";
import { OverlayProvider } from "../../ui/overlay";
import { ProjectConfigPanel } from "./ProjectConfigPanel";

function renderPanel(onSave = vi.fn(), onClose = vi.fn()) {
  const project = makeMockProjects()[0];
  return { project, onSave, onClose, ...render(<OverlayProvider>
    <ProjectConfigPanel open project={project} onClose={onClose} onSave={onSave} />
  </OverlayProvider>) };
}

it("keeps project information and cover choice without a second asset manager", async () => {
  const user = userEvent.setup();
  const { onSave } = renderPanel();
  const dialog = screen.getByRole("dialog", { name: "项目配置" });
  expect(within(dialog).queryByText("资产管理")).not.toBeInTheDocument();
  expect(within(dialog).queryByText("任务回收站")).not.toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "选择图片" }));
  expect(screen.getByRole("dialog", { name: "选择封面图片" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "设为封面" }));
  await user.click(within(dialog).getByRole("button", { name: "保存" }));
  expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ cover: expect.objectContaining({ kind: "asset" }) }));
  expect(onSave.mock.calls[0]).toHaveLength(1);
});

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
  await user.click(screen.getByRole("button", { name: "保存" }));
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
  expect(onSave.mock.calls[1]).toEqual(onSave.mock.calls[0]);
});
